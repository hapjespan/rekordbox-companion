# KICKOFF: Rekordbox Companion (Browser Edition)

> Spec-driven kick-off document. Primary input for Phase 1 (Understand) of
> the Agent Workflow Graph; run the bootstrap prompt first, then feed this
> document into `/grill-with-docs`. Suggested `specs/PROFILE.md`:
> `gate_mode: standard`, `deliverable_type: proof-of-value`,
> `project_type: greenfield`, `tracker: github`. Sections marked `[AGENT]`
> contain hard rules for AI agents working in this repo (mirror into CLAUDE.md).

---

## 1. Problem Statement

A working DJ maintains a Rekordbox library (encrypted SQLite `master.db`) and
receives song requests and references as Spotify playlists. Today there is no
fast way to (a) match a Spotify playlist against the local collection,
(b) turn the matches into a Rekordbox playlist, (c) see which tracks are
missing and acquire them via Apple Music / iTunes Store, and (d) organize
playlists per booking type (horeca, wedding, private party, theme party)
based on play counts and existing playlists. Doing this manually costs
hours per booking.

## 2. Goals

- G1: Match a Spotify playlist against the local Rekordbox collection in
  under 30 seconds for a 100-track playlist, with >= 95% correct automatic
  matches on well-tagged libraries.
- G2: Create a Rekordbox playlist from matched tracks in one action, with
  an automatic `master.db` backup before every write.
- G3: Produce a "missing tracks" queue where every row links directly to the
  correct track page on Apple Music / iTunes Store (NL storefront).
- G4: Generate a booking-type folder/playlist structure proposal from
  per-track play counts + the existing playlist tree, writable back to
  Rekordbox as folders.
- G5: Preview/play any track in the collection from the browser. Library is
  mp3/m4a (AAC): both stream natively. Server-side ffmpeg transcode is the
  fallback for non-native codecs (ALAC-in-m4a, future AIFF/WAV additions).

## 3. Non-Goals (v1)

- NG1: No cloud/multi-user deployment. Single user, localhost only.
  (Reason: master.db write path must be local; auth/hosting is a v2 topic.)
- NG2: No downloading or ripping of audio from Spotify or Apple Music.
  Store deep links only. (Legal boundary.)
- NG3: No editing of Rekordbox track metadata (tags, cues, grids).
  Read collection + write playlists/folders only. (Risk containment.)
- NG4: No pixel-perfect waveforms in v1. Basic playback + progress bar
  first; ANLZ waveform rendering is P2.
- NG5: No native app packaging (Electron/Tauri). Browser + local server only.

## 4. Architecture Decision

**Local-first web app.** One process on the DJ machine serves everything.

```
Browser (React SPA, rekordbox dark theme)
   |
   |  HTTP + SSE, 127.0.0.1:8787
   v
FastAPI (Python 3.12)
   |-- pyrekordbox ------> Rekordbox master.db (SQLCipher)   [read + guarded write]
   |-- app.sqlite -------> own data: bookings, tags, match cache, sync state
   |-- Spotify Web API --> playlist contents (OAuth PKCE, loopback redirect)
   |-- iTunes Search API -> missing-track store links (no auth)
   |-- ffmpeg -----------> fallback transcode for non-native codecs
   '-- serves the built React SPA as static files
```

**Rekordbox version pin: 7.2.17.** Auto-update in Rekordbox is disabled for
the project duration. Since Rekordbox 6.6.5 the SQLCipher key is no longer
extractable from the local install; acquire it once in Phase 0 via
`python -m pyrekordbox download-key`. Upgrading Rekordbox is a deliberate,
gated action: check pyrekordbox changelog, backup, upgrade, re-verify
`/api/health` version match.

Constraints that drive this decision:

- `master.db` lives at `~/Library/Pioneer/rekordbox/` (macOS) or
  `%AppData%\Pioneer\rekordbox\` (Windows). Writes must happen on that
  machine. Therefore the backend runs locally; the browser is only UI.
- Bind to `127.0.0.1` exclusively. No remote access in v1.
- The Debian server is out of scope for v1. P2: nightly read-only mirror of
  collection + history to central Postgres for analytics.

## 5. Stack

| Layer      | Choice                                      | Notes |
|------------|---------------------------------------------|-------|
| Backend    | Python 3.12, FastAPI, uvicorn               | single process, serves API + SPA |
| RB access  | pyrekordbox                                 | only library allowed to touch master.db |
| Matching   | rapidfuzz                                   | fuzzy artist/title scoring |
| Own data   | SQLite via SQLAlchemy 2.x + Alembic         | file: `data/app.sqlite` |
| Audio      | HTTP Range streaming; ffmpeg fallback        | mp3/AAC native; transcode only for ALAC/AIFF |
| Frontend   | React 18, TypeScript, Vite, Tailwind v4     | SPA, built into `web/dist` |
| Design     | Delivered token set in `web/design-input/`  | DESIGN.md, tokens.json, variables.css, theme.css (Tailwind `@theme`) |
| State/data | TanStack Query + Zustand                    | server state vs UI state |
| Player     | HTML5 `<audio>` against stream endpoint     | |
| Tooling    | uv (Python), pnpm (JS), ruff, pytest, vitest, Playwright | |

## 6. Repository Structure

```
rekordbox-companion/
  KICKOFF.md
  CLAUDE.md                  # agent rules (see section 12)
  Makefile                   # dev, test, build, run
  engine/                    # Python backend
    pyproject.toml
    src/companion/
      main.py                # FastAPI app factory, static mount
      config.py              # paths, env, rekordbox detection
      rb/                    # pyrekordbox adapter layer (ONLY module that imports pyrekordbox)
        reader.py            # collection, playlists, play counts
        writer.py            # guarded playlist/folder writes
        backup.py            # timestamped master.db backups
        guard.py             # rekordbox-running detection, version pin check
      matching/
        normalize.py         # title/artist normalization rules
        engine.py            # ISRC exact + fuzzy pipeline, scoring
      integrations/
        spotify.py           # OAuth PKCE, playlist fetch
        itunes.py            # iTunes Search API client (country=NL)
      audio/
        stream.py            # Range requests, ffmpeg transcode pipe
      bookings/
        models.py            # booking types, genre tags
        structurer.py        # folder/playlist structure generation
      db/                    # own SQLite: models, session, migrations
      api/                   # routers: collection, sync, missing, bookings, player
    tests/
  web/                       # React frontend
    design-input/            # delivered: DESIGN.md, tokens.json, variables.css, theme.css
    src/
      theme/                 # theme.css imported as Tailwind @theme + semantic aliases
      components/            # TrackTable, Player, MatchReview, Sidebar...
      features/
        collection/
        spotify-sync/
        missing/
        bookings/
      api/                   # generated client from OpenAPI
    tests/
  data/                      # app.sqlite, backups/ (gitignored)
  scripts/
    dev.sh                   # starts uvicorn --reload + vite dev with proxy
```

## 7. Own Data Model (app.sqlite)

```
sync_session(id, spotify_playlist_id, spotify_snapshot_id, name, created_at, status)
sync_track(id, sync_session_id, spotify_track_id, isrc, artist, title, duration_ms,
           match_status[matched|review|missing|rejected],
           rb_content_id NULL, match_score, matched_at)
missing_track(id, sync_track_id, itunes_track_id NULL, itunes_url NULL,
              status[open|acquired|ignored], resolved_at NULL)
booking_profile(id, name, slug)           # seeded: horeca, bruiloft, prive, thema
booking_profile_genre_tag(booking_profile_id, tag)
structure_proposal(id, booking_profile_id, generated_at, payload_json, applied_at NULL)
app_config(key, value)
```

**Signal sources for the structure generator.** Rekordbox history is
explicitly ignored (owner decision). The generator reads two signals from
`master.db`: per-track play counts (`djmdContent.DJPlayCount`) and playlist
membership across the existing tree. Note the counter is a lifetime total
with no per-context dimension, so it drives *ranking* within a proposal
while the profile's genre tags (+ BPM ranges) drive the *split* into
booking types.

Rekordbox data is never duplicated wholesale; `rb_content_id` references
suffice. A lightweight in-memory index of the collection (id, artist, title,
duration, isrc, genre, bpm, location) is rebuilt on demand and cached.

## 8. API Contract (v1)

```
GET  /api/health                          # incl. rekordbox version, db path, guard status
GET  /api/collection?query=&limit=&offset=
GET  /api/collection/reindex        POST  # rebuild matching index
GET  /api/playlists                       # rekordbox playlist tree
GET  /api/config | PUT

POST /api/sync/sessions {spotify_playlist_url}   # fetch + auto-match, returns session
GET  /api/sync/sessions/{id}                     # tracks with match status
POST /api/sync/sessions/{id}/tracks/{tid}/accept {rb_content_id}
POST /api/sync/sessions/{id}/tracks/{tid}/reject
POST /api/sync/sessions/{id}/apply {playlist_name, parent_folder_id?}
     # -> backup, guard check, write playlist, return created rb playlist id

GET  /api/missing?status=open
POST /api/missing/{id}/resolve {status}
POST /api/missing/refresh-links                  # re-run iTunes lookups

GET  /api/profiles ... CRUD                      # booking profiles + genre tags
POST /api/structure/proposals {booking_profile_id}  # generate proposal
POST /api/structure/proposals/{id}/apply         # write folders/playlists to RB

GET  /api/player/stream/{rb_content_id}          # Range support; transcodes if needed
GET  /api/auth/spotify/login | /callback         # PKCE loopback flow
```

OpenAPI schema is the single source of truth; the frontend client is
generated from it (`pnpm openapi`). Backend and frontend teams/agents may
not drift from this contract without updating the schema first.

## 9. Matching Pipeline (spec)

Local library is mp3/m4a without ISRC tags, so fuzzy matching is the
primary path. ISRC stays as an opportunistic fast lane: at index time,
read `djmdContent.ISRC` (zero extra cost); if ever populated, it wins.

1. Normalize: lowercase, strip `(feat. ...)`, `- remastered`, brackets,
   punctuation, diacritics; keep remix/edit markers as a separate token.
2. Tier 1 (opportunistic): ISRC exact match when present -> auto-match.
   Expected hit rate near zero on this library; do not invest UI in it.
3. Tier 2 (primary): normalized artist+title exact AND duration within
   +/- 3s -> auto-match.
4. Tier 3 (primary): rapidfuzz token_set_ratio on artist+title, weighted
   40/60, duration penalty beyond +/- 5s. Score >= 92 -> auto-match,
   75 to 92 -> review queue (top 3 candidates), < 75 -> missing.
5. Remix guard: differing remix tokens can never auto-match (forced review).

Because fuzzy is primary, the review UI (Phase 2) and the golden test set
below carry more weight than in an ISRC-rich library. Budget accordingly.

Acceptance: golden test set of >= 50 real pairs (including 10 nasty cases:
remixes, "radio edit", featuring variants) with expected outcomes in
`engine/tests/fixtures/matching_golden.yaml`.

## 10. Phased Plan

### Phase 0: Foundation (P0)
Repo scaffold per section 6, Makefile, CI (lint + test on push),
config detects Rekordbox install + master.db on macOS and Windows,
SQLCipher key acquired (`python -m pyrekordbox download-key`),
pyrekordbox smoke test reads collection count from Rekordbox 7.2.17.
Read-only. Design input files committed to `web/design-input/`.
DoD: `make dev` serves SPA shell on 127.0.0.1:8787, `/api/health` green
and reporting version 7.2.17 match.

### Phase 1: Collection browser + player (P0)
- As a DJ, I want to search my collection and play any track in the browser
  so that I can verify matches by ear.
- Track table (virtualized, 10k+ rows), search, sort; bottom player bar.
- mp3 and m4a (AAC) stream directly with Range support. ffmpeg fallback
  path implemented and tested against an ALAC or AIFF fixture file, since
  the live library will not exercise it.
DoD: an mp3 and an m4a from the real library both play; the transcode
fallback passes its fixture test; search under 100ms on a 10k collection.

### Phase 2: Spotify sync (P0)
- As a DJ, I want to paste a Spotify playlist URL and get an instant
  match report so that I know what I own.
- As a DJ, I want to resolve doubtful matches with keyboard only
  (arrow keys, A=accept, R=reject, space=preview) so that review is fast.
- As a DJ, I want one button that creates the Rekordbox playlist from all
  matches so that the result appears in Rekordbox after restart/refresh.
- Write path: guard (Rekordbox must be closed) -> timestamped backup ->
  write via pyrekordbox -> verify readback.
DoD: golden matching tests pass; created playlist visible and intact in
Rekordbox; backup file exists per write.

### Phase 3: Missing tracks to Apple Music (P0)
- As a DJ, I want every missing track to show an Apple Music / iTunes link
  (NL storefront) so that acquiring it is one click away.
- iTunes Search API lookup (term = artist + title, `country=NL`,
  `entity=song`), best-effort auto-pick + manual override, copy button,
  status tracking (open/acquired/ignored).
DoD: >= 90% of missing tracks in test set resolve to a correct store link.

### Phase 4: Booking profiles + structure generator (P1)
- As a DJ, I want to define booking profiles (horeca, bruiloft, prive,
  thema) with genre tags and optional BPM ranges so that my collection can
  be sliced per booking type.
- As a DJ, I want a generated folder/playlist structure proposal per
  profile, driven by playlist membership and per-track play counts
  (`DJPlayCount`), so that prep time drops. Rekordbox history is ignored
  by design; play counts rank tracks, profile tags define the split.
- As a DJ, I want to edit the proposal as a tree (rename, drop, move)
  before applying so that nothing lands in Rekordbox unreviewed.
- Rule-based v1 (genre tags + BPM buckets + play-count ranking).
  LLM-assisted clustering is P2 behind a feature flag.
DoD: proposal renders as editable tree; apply writes folders + playlists to
Rekordbox with the same guard/backup path as Phase 2.

### Phase 5: Theme polish (P1)
- Design source of truth is the delivered token set (`web/design-input/`):
  Spotify dark system per DESIGN.md ("nocturnal jukebox control room").
  Surfaces void-black/carbon/graphite/smoke, spotify-green strictly as
  accent (play/active states, never primary CTA), white pill as primary
  action, radius families 6px content / 9999px actions / 500px inputs,
  elevation via surface shifts instead of shadows.
- Rekordbox contribution is information density, not color: compact track
  tables (11-13px rows), keyboard-first workflows, sidebar tree.
- Font: SpotifyMixUI is proprietary and must not ship; use the substitute
  stack from DESIGN.md (Inter + system-ui) under the same token names.
- Keyboard map overlay, empty states, error toasts.
DoD: every rendered color/space/radius traces to a token from
`web/design-input/theme.css`; DESIGN.md Do's and Don'ts pass as a review
checklist; side-by-side screenshot review approved by owner.

### P2 parking lot
ANLZ waveform rendering, Debian/Postgres read-only mirror, LLM structure
suggestions, multi-device access with auth, auto-watch Spotify playlists
for changes (snapshot_id polling).

## 11. Risks

| Risk | Mitigation |
|---|---|
| master.db corruption on write | Guard: refuse writes while Rekordbox runs; timestamped backup before every write; readback verification; writes only via `rb/writer.py` |
| Rekordbox update changes schema/encryption | Pinned to 7.2.17 in `config.py`; auto-update disabled in Rekordbox; `/api/health` warns on mismatch; check pyrekordbox release notes before unpinning |
| Spotify API quota / app review | Personal-use app in dev mode is sufficient for single user |
| SpotifyMixUI font is proprietary | Never bundle it; Inter + system-ui substitute per DESIGN.md, mapped under the same font tokens |
| iTunes Search mismatches | Manual override in UI; store both auto and chosen link |
| ffmpeg missing on machine | Startup check with clear install instruction (brew/winget) |

## 12. `[AGENT]` Rules (mirror into CLAUDE.md)

1. Never import pyrekordbox outside `engine/src/companion/rb/`.
2. Never add a write operation to `master.db` outside `rb/writer.py`, and
   every write goes through `guard.check()` + `backup.create()` first.
   No exceptions, including tests (tests use a fixture copy of master.db).
3. Never commit real `master.db`, backups, tokens or `data/` contents.
4. API changes start in the OpenAPI schema; regenerate the client before
   touching frontend code.
5. Frontend colors/typography/spacing/radius only via the tokens in
   `web/design-input/theme.css`, never hardcoded values. Never bundle or
   reference SpotifyMixUI font files; the substitute stack ships under the
   original token names. DESIGN.md Do's and Don'ts are binding in review.
6. Code, comments, commits in English. UI copy in Dutch.
7. Each phase lands as its own PR with tests; golden matching fixtures may
   only be extended, never weakened.

## 13. Decision Log & Open Questions

Resolved (2026-08-16, owner):

- D1: Rekordbox version pinned at **7.2.17**; auto-update disabled.
- D2: Library is mp3/m4a without ISRC tags. Fuzzy matching is primary;
  ISRC is an opportunistic fast lane only. Audio streams natively;
  ffmpeg is fallback.
- D3: Design source of truth is the delivered Spotify token set in
  `web/design-input/` (DESIGN.md + tokens.json + variables.css + theme.css).
  Font substitute: Inter. Rekordbox contributes density and workflow, not
  its color scheme.
- D4 (superseded, final): Rekordbox history is **ignored entirely**.
  The structure generator works from playlist membership and per-track
  play counts (`djmdContent.DJPlayCount`) only. No session linking, no
  archive folders, no booking backfill import.

Open:

- [Engineering, non-blocking, Phase 0] Verify `djmdContent.ISRC` fill rate
  on the real DB (one query) to confirm the near-zero assumption behind D2.

## 14. Dev Setup

```bash
# prerequisites: uv, pnpm, ffmpeg, Rekordbox installed locally
git clone <repo> && cd rekordbox-companion
make setup      # uv sync + pnpm install + pre-commit hooks
make dev        # uvicorn :8787 with reload + vite dev proxy
make test       # pytest + vitest
make build      # vite build -> web/dist, served by FastAPI in prod mode
make run        # single-process production mode on 127.0.0.1:8787
```
