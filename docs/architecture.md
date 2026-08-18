# Architecture: modules and seams

Phase 4 deliverable, 2026-08-16. Written in the `codebase-design` vocabulary:
a **module** is an interface plus an implementation; a **seam** is where an
interface lives and behaviour can be swapped without editing call sites; an
**adapter** satisfies an interface at a seam; a module is **deep** when a small
interface hides a lot of behaviour. The seams named here are the seams the
phase 6 tests use — that is the phase 4 exit criterion, so changing a seam
later means changing this document first.

## System shape

```
Browser SPA (React, generated client)
    │  seam 5: OpenAPI schema (HTTP, 127.0.0.1:8787)
    ▼
FastAPI routers (thin; orchestration only)
    │            │              │               │
    ▼            ▼              ▼               ▼
 rb (seam 1)  matching      enrichment      integrations
 pyrekordbox  (seam 2)      (seam 3)        (seam 4: spotify, itunes)
    │         pure module      │  GenreSource      │ httpx → fixed hosts
    ▼                          ▼                    ▼
 master.db              app.sqlite (db module)   external APIs
 (+ backups)
```

## Seam 1 — the `rb` interface (`engine/src/companion/rb/`)

**Interface**: `snapshot() → CollectionIndex`, `playlist_tree()`,
`create_playlist(name, parent) → rb_id`, `create_folder(name, parent) → rb_id`,
`add_tracks(rb_id, content_ids) → added`, `guard_check() → ok | refusal`,
`backup() → path`, `readback(rb_id) → track_ids`. Nothing else: no metadata
mutation exists on this interface, which makes constitution Principle III
unrepresentable rather than merely forbidden.

**Depth**: very deep. Behind those eight calls sit SQLCipher, pyrekordbox's
session and update-sequence bookkeeping, version pinning, process detection,
disk-headroom checks and rotating zipped backups (ADR 0016). Callers know none
of it.

**Adapters**: (1) the real pyrekordbox implementation, integration-tested
against the fixture `master.db`; (2) an in-memory fake for API-layer tests.
Two adapters, so the seam is real, not hypothetical.

**Locality**: every Rekordbox-format risk (the 7.2.17 pin, a future schema
change) lands in this one directory. Project rule 1 (no pyrekordbox imports
elsewhere) is the seam discipline, enforced in review and by a lint check.

## Seam 2 — the matching engine (`engine/src/companion/matching/`)

**Interface**: `match(spotify_tracks, index) → [Outcome]` where `Outcome` is
`auto(content_id, score) | review(candidates) | missing | unmatchable`, plus
`normalize(artist, title) → NormForm`. Pure functions: no IO, no clock, no
database — dependencies come in as arguments.

**Depth**: the entire tiered pipeline (ISRC lane, exact lane, fuzzy scoring
40/60 with duration penalty, thresholds 92/75, remix guard) is implementation.
A threshold change never touches a caller.

**Test surface**: the golden set (`matching_golden.yaml`) exercises exactly
this interface. That satisfies the deletion test: remove the module and all
of US1's complexity reappears in the sync router.

## Seam 3 — `GenreSource` (`engine/src/companion/enrichment/`)

**Interface**: `genres_for(track: IndexEntry) → [genre] | NoneFound`, plus the
runner's `enqueue_pending()`, `run(budget) → progress`. Manual overrides are
not a source: they live in the db module and the runner refuses to touch any
track that has one (FR-028), so the precedence rule sits in one place.

**Adapters**: `musicbrainz` (sole adapter, 1 req/s, tags ranked by count).
The coverage spike (research R1) found Spotify artist genres unavailable to
this app (ADR 0018 supersedes ADR 0013's Spotify-primary ordering); the seam
still exists so a reserve adapter (Last.fm) can be added without a redesign
if MusicBrainz's real-collection coverage falls short of SC-008.

**Locality**: free-tier rate limiting, retry and resumability (ADR 0011/0013)
are runner implementation; a new source is a new adapter, not a redesign.

## Seam 4 — external integrations (`engine/src/companion/integrations/`)

**Interface**: `spotify.playlist(id) → [SpotifyTrack]`, `spotify.auth_*`,
`spotify.player_token()`, `itunes.search(artist, title) → StoreLink | None`.

**Adapters**: real httpx clients (outbound hosts fixed: api.spotify.com,
itunes.apple.com, musicbrainz.org — the SSRF answer from constraints) and
recorded-response fakes for tests. OAuth PKCE state and token refresh are
implementation, invisible to routers.

## Seam 5 — the OpenAPI schema (engine ↔ SPA)

**Interface**: the FastAPI OpenAPI export; `contracts/api.md` is its design.
The SPA's generated client (`openapi-typescript` + `openapi-fetch`) is an
adapter that is regenerated, never edited (rule 4). Contract tests pin the
refusal codes of the two apply endpoints because they encode the guard.

**Why the seam sits here** and not at a BFF or per-feature API layer: one
process, one consumer; anything thicker fails the deletion test.

## Modules without their own seam

- **API routers**: deliberately shallow — validation in, module calls,
  response out. Their correctness is contract-tested through seam 5.
- **db module**: SQLAlchemy models and migrations for `data-model.md`; a
  conventional repository layer was rejected (see plan; single consumer per
  table, SQLAlchemy's session is already the seam the tests fake).
- **audio/stream**: Range handling and the ffmpeg pipe; tested with fixture
  files directly, its interface is one streaming endpoint.
- **SPA features**: each feature folder consumes the generated client and the
  token theme; the review queue's keyboard state machine is the one deep
  frontend module (vitest-covered), everything else is composition.

## Where change is expected, and where it lands

| Likely change | Lands in |
|---|---|
| Rekordbox version unpin / schema drift | seam 1 implementation only |
| Matching threshold tuning after golden-set growth | seam 2 implementation + fixtures |
| Enrichment source swap or addition | one adapter at seam 3 |
| Spotify API quirks, token policy changes | seam 4 implementation |
| New endpoint or payload change | schema first (seam 5), then both sides |
| P2 items (waveforms, Postgres mirror, LLM suggestions) | new modules behind existing seams; no seam moves |
