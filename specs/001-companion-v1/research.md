# Research: Rekordbox Companion v1

Phase 0 output of `/speckit-plan`, 2026-08-16. The stack itself is fixed input
(kickoff section 5, constitution); research here resolves the choices the stack
leaves open and turns the three open unknowns from `docs/constraints.md` into
scoped spikes with fallbacks. No NEEDS CLARIFICATION markers remained in the
technical context.

## R1. Genre enrichment sources

- **Decision**: One `GenreSource` seam with two adapters, tried in order:
  Spotify artist genres (primary; the app already holds an authorized Spotify
  session, genres are artist-level, zero extra auth) and MusicBrainz genre tags
  (secondary; open data, no key, hard rate limit of 1 request/second).
  Enrichment runs incrementally and resumably (queue with per-track state), not
  as a bulk pass, because 20.000+ tracks against a 1 req/s source is a
  multi-hour job that will be interrupted.
- **Rationale**: Both are free-tier (ADR 0011), both cover mainstream Western
  pop/dance repertoire well, and artist-level genres are good enough for
  Booking Profile filtering, which works on coarse tags (spec US7). The seam
  makes the spike cheap: measure coverage per adapter on the fixture library,
  drop or add an adapter without touching the orchestrator.
- **Alternatives considered**: Last.fm tags (free key, but tags are folksonomy
  noise: "seen live" outranks genres; kept as reserve adapter only), Discogs
  (strict rate limits plus OAuth for meaningful quota), paid providers
  (killed by ADR 0011).
- **Spike** (unknown #2): run both adapters over the fixture collection,
  report coverage % and a 50-track sample for owner judgement against SC-008
  (≥80% coverage, ≥90% sample quality).

## R2. Spotify full-track playback in the review UI

- **Decision**: Spotify Web Playback SDK, initialised in the SPA with a token
  from the backend's PKCE session, spiked in the first implementation slice
  that touches review. `127.0.0.1` is a secure context in Chromium and
  Firefox, so the SDK's secure-context requirement is met on localhost; the
  real risk is EME/Widevine availability in the owner's browser.
- **Rationale**: ADR 0009 already commits to embedded full-track playback;
  Premium is available. The spike only confirms the environment.
- **Alternatives considered**: Spotify 30-second preview URLs (rejected:
  Spotify stopped issuing preview URLs to new Web API apps in late 2024, so a
  new app cannot rely on them), opening the track in the Spotify desktop
  client via deep link (kept as the fallback, not the primary).
- **Spike** (unknown #3): SDK connect + play one full track from the review
  screen on the dev machine's browser. Fallback if it fails: local preview
  plus a `spotify:track:` deep link per review item; ADR 0009 gets amended.

## R3. pyrekordbox write compatibility with Rekordbox 7.2.17

- **Decision**: Treat pyrekordbox's Rekordbox-6-format database API as the
  write path (Rekordbox 7 continues the v6 `master.db` SQLCipher format), and
  gate all write-path work behind a smoke-test spike on the fixture database:
  create playlist, create folder, add tracks, readback, and verify the
  database still opens cleanly.
- **Rationale**: pyrekordbox documents playlist and folder creation against
  the v6 database and handles the update-sequence bookkeeping Rekordbox needs;
  the version pin (ADR 0002) freezes the schema risk. What cannot be verified
  here is Rekordbox itself reading the result — that final check runs on the
  owner's Mac (documented in `quickstart.md`).
- **Alternatives considered**: writing XML export/import instead of the
  database (rejected: Rekordbox 7 imports XML manually and it does not update
  the live tree the DJ uses), driving the Rekordbox UI (rejected: fragile, and
  the guard requires Rekordbox closed anyway).
- **Spike** (unknown #1): first task of the write-path work; a failure here
  stops phase 6 and reopens phase 4, per the workflow's constraint rule.

## R4. Progress events to the SPA

- **Decision**: Server-Sent Events on one `/api/events` channel for sync and
  enrichment progress; plain request/response for everything else.
- **Rationale**: Sync (up to 1.000 tracks) and enrichment (hours, resumable)
  are long-running; SSE is one-directional, trivial over localhost, and
  reconnects natively in the browser. Matches kickoff's "HTTP + SSE".
- **Alternatives considered**: WebSockets (rejected: nothing flows
  client-to-server mid-run), polling (rejected: enrichment runs for hours;
  polling either lags or spams).

## R5. Frontend client generation from OpenAPI

- **Decision**: FastAPI's OpenAPI export is the schema of record
  (`pnpm openapi` regenerates); TypeScript client generated with
  `openapi-typescript` (types) + `openapi-fetch` (runtime).
- **Rationale**: Project rule 4 mandates schema-first; these two are boring,
  actively maintained, dependency-light, and keep the generated surface small
  enough to read.
- **Alternatives considered**: orval (heavier, generates react-query hooks we
  would fight given TanStack Query is hand-wired to Zustand state), hand-written
  fetch layer (rejected: drift is exactly what rule 4 exists to prevent).

## R6. Collection index and search

- **Decision**: One in-memory collection index (id, artist, title, duration,
  isrc, bpm, genre, play count, location), rebuilt on demand from `master.db`
  reads and cached in the process; it serves both matching and the collection
  search endpoint. Substring search over normalised artist+title, measured at
  30.000 tracks.
- **Rationale**: 30.000 rows of short strings is a few tens of MB; a single
  process (ADR 0001) owns it; no staleness protocol is needed beyond an
  explicit reindex action. rapidfuzz against an in-memory list stays inside
  the 30s/100-track budget by orders of magnitude.
- **Alternatives considered**: mirroring the collection into the app's SQLite
  with FTS5 (rejected: introduces a second copy of Rekordbox data with a sync
  protocol, against the "reference, never duplicate" rule in kickoff §7);
  querying `master.db` per keystroke (rejected: SQLCipher open cost and it
  couples UI latency to Rekordbox file locks). Recorded as ADR 0012.

## R7. Testing shape

- **Decision**: pytest for the engine with the golden matching set
  (`engine/tests/fixtures/matching_golden.yaml`) as the gate on the matching
  seam; write-path integration tests against a fixture `master.db` copy;
  FastAPI api tests against an in-memory fake of the `rb` interface; vitest
  for SPA units (review-queue key handling above all); Playwright smoke e2e
  for the two core flows (sync→review→apply, missing→link) once the UI
  exists.
- **Rationale**: Tests live at the seams named in `docs/architecture.md`; the
  golden set is constitutionally protected (Principle IV).
- **Alternatives considered**: mocking pyrekordbox inside `rb` tests
  (rejected: the fixture database is the point — the risk is the real file
  format, not our code around it).
