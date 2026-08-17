# Implementation Plan: Rekordbox Companion v1

**Branch**: `001-companion-v1` | **Date**: 2026-08-16 | **Spec**: `specs/001-companion-v1/spec.md`

**Input**: Feature specification from `/specs/001-companion-v1/spec.md`

## Summary

A single local process (FastAPI, `127.0.0.1:8787`) serves a React SPA and owns
four capabilities: matching Spotify playlists against a 30.000+ track Rekordbox
Collection (fuzzy-primary pipeline gated by a golden set), a guarded add-only
write path into `master.db` via pyrekordbox, a missing-tracks-to-store-links
queue, and hand-designed booking structures fed by app-side genre enrichment.
The architecture is organised around five seams (see
`docs/architecture.md`): the `rb` interface over pyrekordbox, the pure matching
engine, the `GenreSource` enrichment seam, the external-API integrations, and
the OpenAPI schema between engine and SPA. Three spikes precede feature depth:
pyrekordbox 7.2.17 write compatibility, enrichment coverage, and the Spotify
Web Playback SDK on localhost (research R1-R3).

## Technical Context

**Language/Version**: Python 3.12 (engine, uv-managed), TypeScript 5.x (web)

**Primary Dependencies**: FastAPI + uvicorn, pyrekordbox (confined to
`engine/src/companion/rb/`), rapidfuzz, SQLAlchemy 2.x + Alembic, httpx;
React 18, Vite, Tailwind v4, TanStack Query + Zustand, openapi-typescript +
openapi-fetch (R5); ffmpeg (binary, transcode fallback)

**Storage**: `data/app.sqlite` (companion-owned, data-model.md);
`master.db` (Rekordbox, SQLCipher, read + guarded playlist/folder writes only);
in-memory collection index as cache (R6/ADR 0012)

**Testing**: pytest (golden matching set, fixture-`master.db` integration,
API tests against a fake `rb` adapter), vitest (SPA units), Playwright (two
core-flow smoke e2e) — R7

**Target Platform**: the DJ's Mac in production; Linux dev container here;
browser is UI only (ADR 0001)

**Project Type**: web application, single-process backend + SPA (kickoff §6)

**Performance Goals**: match report ≤ 30s / 100 tracks; collection search
≤ 100ms/keystroke at 30.000+ (tested at 40.000); playlists to 999 tracks
(larger refused before the session starts)

**Constraints**: `docs/constraints.md` — rotating zipped backups, newest 10
(ADR 0016),
free-tier-only external services (ADR 0011), NIS2 logging plan (tokens/key
never logged), ASVS-mapped requirements, localhost-only

**Scale/Scope**: 1 user, 1 machine; 30.000+ tracks; 7 user stories, ~25
endpoints (contracts/api.md)

## Constitution Check

*GATE: passed pre-research; re-checked after design — no violations.*

- **I. Local-first, single-user**: one process, `127.0.0.1:8787`, SPA served
  as static files; no cloud component appears anywhere in this plan. PASS.
- **II. Guarded writes**: exactly two write endpoints (sync apply, structure
  apply), both routed through `rb/writer.py` behind `guard.check()` +
  `backup.create()` + readback; `write_log` table audits each (data-model).
  Tests use a fixture `master.db`. PASS.
- **III. Read-only collection, no metadata edits**: the `rb` interface exposes
  no metadata mutation at all — the seam makes the violation unrepresentable
  rather than forbidden. Enrichment stores genres app-side only (FR-030). PASS.
- **IV. Fuzzy matching primary**: matching engine is a pure module whose only
  gate is the golden set; ISRC fast lane costs one index field, no UI. PASS.
- **V. Design tokens binding**: SPA consumes `web/design-input/theme.css` as
  the Tailwind `@theme`; no hardcoded values; Inter substitute under original
  token names. Enforced in phase 6 review per story. PASS.
- **Engineering baseline**: TDD per task, two-axis review, atomic commits,
  phase-per-PR, schema-first API (R5) — all reflected in the task and testing
  shape. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-companion-v1/
├── plan.md              # this file
├── research.md          # R1-R7: sources, spikes, rejected alternatives
├── data-model.md        # app.sqlite schema + in-memory index
├── quickstart.md        # run + validation scenarios per story
├── contracts/
│   └── api.md           # HTTP contract; OpenAPI export is schema of record
└── tasks.md             # phase 5 output (/speckit-tasks), not created here
```

### Source Code (repository root)

```text
engine/
  pyproject.toml
  src/companion/
    main.py              # app factory, static mount, SSE channel
    config.py            # paths, env, version pin (rule 1 moved Rekordbox
                         #   detection into rb/reader.py, phase 6 build)
    rb/                  # ONLY module importing pyrekordbox (rule 1)
      reader.py          #   collection snapshot, playlist tree, play counts,
                         #   Rekordbox install/version detection
      writer.py          #   guarded playlist/folder writes, add-only updates
      backup.py          #   timestamped zipped backups, newest 10 (ADR 0016)
      guard.py           #   running-check, version pin, disk headroom
      index.py           #   in-memory collection index (R6/ADR 0012)
    matching/
      normalize.py       # normalisation + remix-token extraction (FR-004)
      engine.py          # tiered pipeline, scoring, classification (FR-005..008)
    enrichment/
      source.py          # GenreSource seam (ADR 0013)
      spotify_genres.py  # adapter 1
      musicbrainz.py     # adapter 2
      runner.py          # incremental resumable queue
    integrations/
      spotify.py         # OAuth PKCE, playlist fetch, player token
      itunes.py          # Search API, country=NL
    audio/
      stream.py          # Range streaming, ffmpeg pipe fallback
    bookings/
      models.py          # profiles, structures, suggestions query
    db/                  # SQLAlchemy models, session, Alembic migrations
    api/                 # routers: health, collection, auth, sync, missing,
                         #   enrichment, profiles, structures, player, events
  tests/
    fixtures/            # matching_golden.yaml, fixture master.db (untracked),
                         #   audio fixtures incl. one ALAC
web/
  design-input/          # delivered tokens (binding, ADR 0004)
  src/
    theme/               # theme.css as Tailwind @theme
    api/                 # generated client (openapi-typescript + openapi-fetch)
    components/          # TrackTable, PlayerBar, KeymapOverlay, Tree
    features/
      collection/  spotify-sync/  review/  missing/  enrichment/  bookings/
  tests/                 # vitest; e2e/ Playwright smoke flows
data/                    # app.sqlite, backups/ (gitignored, rule 3)
scripts/dev.sh
Makefile
```

**Structure Decision**: kickoff §6 layout, with two deltas the spec forced:
`bookings/structurer.py` (the old generator) is replaced by a suggestions
query in `bookings/models.py` (ADR 0008), and a new `enrichment/` module
carries the D7 scope. `rb/index.py` is new: the collection index lives behind
the `rb` seam because it is a cache of `master.db`, not app data.

## Constraint-to-decision map

Phase 4 exit criterion: every constraint from `docs/constraints.md` maps to a
decision or an explicitly accepted risk with an owner.

| Constraint | Decision / risk |
|---|---|
| 1 user, 1 machine, no concurrency | single process, no auth surface (ADR 0001); SQLite without contention design |
| Playlists ≤ 999 tracks; 30s at 100, 5 min at the cap | in-memory index + rapidfuzz (R6); Spotify pagination fetch; SSE progress (R4); cap enforced before the session starts |
| Collection 30.000+, tested at 40.000 | index perf test at 40.000 (contracts, quickstart US5); substring search in-process |
| Match/search latency numbers | budgeted against the index, not the DB; perf tests are tasks, not hopes |
| Playback start unbounded (accepted) | no preloading work in v1; owner accepted |
| Best-effort availability, restart as recovery | no supervisor, no health-restart logic; documented in quickstart. Risk accepted, owner: Martien |
| Rotating zipped backups, newest 10 (ADR 0016) | `backup.py` creates zip, verifies readability, then prunes beyond 10 — prune runs only after a verified create; disk headroom check in `guard.py` refuses writes when a backup would not fit |
| Free-tier-only services (ADR 0011) | GenreSource adapters: Spotify genres + MusicBrainz at 1 req/s; enrichment incremental + resumable (ADR 0013) |
| No deadline | spikes ordered first anyway: they gate design, not dates |
| NIS2 logging plan | structured logs from `guard`/`backup`/`writer` + `write_log` table; token/key redaction is a log-formatter property, tested |
| ASVS V2/V3/V4 (auth, session, access) | no app auth (out of scope, recorded); tokens in `spotify_auth` with owner-only file perms; disconnect endpoint is the deletion path |
| ASVS V5 (validation) | playlist URL → id parse at the boundary; schema-validated external payloads; SQLAlchemy parameterised throughout |
| ASVS V6/V12 (secrets, files) | `.env` untracked; stream paths resolved only from `rb_content_id` |
| ASVS V10/V14 + SSRF | pinned deps + lockfiles; outbound HTTP restricted to api.spotify.com, itunes.apple.com, musicbrainz.org |
| AVG retention/deletion | `spotify_auth` deleted whole on disconnect (contracts); PII inventory carried forward |
| Unknown #1 pyrekordbox writes | spike gates the write path (R3); failure reopens phase 4 |
| Unknown #2 enrichment coverage | spike with owner judgement against SC-008 (R1) |
| Unknown #3 Playback SDK on localhost | spike; fallback local preview + Spotify deep link, ADR 0009 amended if needed (R2) |

## Deliverable type: proof-of-value — what is deliberately cut

Per `specs/PROFILE.md`, this build proves the idea saves booking-prep time; it
cuts depth, and the cuts are these, on the record:

- **E2E breadth**: Playwright covers the two flows that carry the value claim
  (sync→review→apply and missing→link), not every screen.
- **Player depth**: no waveforms, no gapless, no preload; progress bar + seek.
- **Enrichment depth**: if the spike shows Spotify-genres-only clears SC-008,
  the MusicBrainz adapter is deferred behind its seam rather than built.
- **Error-path polish**: guard refusals and form errors are complete (they
  carry safety and WCAG); rarer failures (SSE reconnect edge cases, partial
  Spotify outages) get logs and a generic Dutch error toast, not bespoke UX.
- **No perf work beyond the stated numbers**: 30s/100 tracks and 100ms search
  are tested; nothing is optimised past them.

Not cut, ever: the guard/backup/readback sequence, the golden set, the token
discipline, keyboard operability. Those are constitutional.

## Complexity Tracking

No constitution violations to justify; the table stays empty.
