# Handover

Phase 8 deliverable. This is the entry point: if you are picking this project up
without having been in the room for any of it, start here and follow the links.
Nothing below duplicates what those documents already say better.

## Start here, in this order

1. **`CLAUDE.md`** — project rules, tech stack, build commands, the index of
   everything else.
2. **`docs/CONTEXT.md`** — what this product is for, the glossary of terms used
   everywhere else, every ADR indexed and linked, and the one-line deployment
   statement.
3. **`scripts/onboarding-wizard.sh`** — run this on the real Mac before doing
   anything else. It walks prerequisites, `make setup`, the SQLCipher key, the
   Spotify Developer app (including a gotcha that cost real debugging time,
   see below), first run, how to observe the running app, and both rollback
   paths. Development in this repository happens in a container against a
   fixture `master.db`; only the wizard's Mac-specific steps need the real
   machine.
4. **`docs/process/workflow.md`** — the Agent Workflow Graph this project was
   built through: nine phases, gate modes, model routing. If more work happens
   on this project through the same graph, read this before starting a phase.

## Current state, as of this handover

- **Phases 0–8 complete.** Gates approved at 2, 4 and 7 (`standard` mode,
  `.workflow/state.json`). This document's own completion is what closes 8.
- **`main` is the released state**, per the workflow's own rule: `release`
  merged into it through a pull request (#172), not pushed directly.
- **All eight user stories are built and reachable** from the delivered
  application shell: Spotify sync and matching, keyboard-first review,
  guarded Rekordbox apply, the missing-tracks buy queue, the collection
  browser and player, genre enrichment, and booking structures with
  suggestions.
- **Test suite**: 534 pytest, 346 vitest, 7 Playwright specs including three
  axe-core accessibility sweeps. All green as of `main`'s tip. CI runs on
  GitHub Actions (`.github/workflows/ci.yml`); it stopped running for part of
  phase 7 on exhausted Actions minutes for this private repository and was
  topped up by the owner — if it goes quiet again, that is the first thing to
  check, not the code.

## What is proven, and what genuinely is not

Read this section before trusting a claim elsewhere in the docs at face value.
Three things stay unproven because they need the owner or the real Mac, not
more code, and no amount of further engineering closes them from here:

- **SC-002 and SC-003** (match accuracy against a real Golden Set): the fixture
  currently holds four illustrative stub cases, not the 50 real cases with 10
  hard cases the spec requires. The matching thresholds (92 auto-match, 75
  review floor) are validated against the stubs and against unit tests of the
  scoring function, not against real DJ data. Owner-supplied real cases close
  this (`specs/001-companion-v1/tasks.md`, T094).
- **SC-009** (booking-prep time under 30 minutes): a manual sign-off after the
  owner prepares one real booking with the app and judges the time against
  their pre-companion baseline (T103). Nothing to measure until that happens.
- **Real hardware behaviour**: whether Spotify Web Playback actually produces
  audio in a real browser with a real Premium session, whether the `itmss://`
  link opens the Music app at the iTunes Store view, and whether a live
  Rekordbox 7.2.17 process holds a lock or cache that would make a backup
  snapshot differ from what this project's tests can see. None of these can be
  verified in the containerized dev environment, which has no Widevine, no
  audio device, and no real Rekordbox install. `specs/001-companion-v1/review-phase-7.md`
  names each explicitly rather than claiming they were tested.

## The one gotcha worth repeating outside the wizard

Real playlist syncs silently failed for a stretch of this project's life, and
it looked exactly like a permissions problem: adding the operator as a
"tester" in the Spotify dashboard changed nothing, because the actual cause
was that Spotify renamed `/playlists/{id}/tracks` to `/playlists/{id}/items`
in a March 2026 API migration, with no advance notice reaching this codebase.
The fix is in `engine/src/companion/integrations/spotify.py`; the lesson is in
`docs/runbook.md`. If real syncs break again with an error that reads like a
permissions issue, check whether Spotify changed its contract again before
spending time on the dashboard.

## What is intentionally not built

Recorded so it reads as a decision rather than an oversight:

- **XML export, per-store checkout, and an automatic watch-folder import** were
  all considered (the delivered design asked for them) and dropped by the
  owner. `specs/001-companion-v1/scope-round-2.md` records why each collided
  with an existing decision (the guarded write path, the single-Store-Link
  design, or the project's own restraint about touching the DJ's file system).
- **Deployment**: `deploy_target: none`, deliberately — see `docs/CONTEXT.md`'s
  Deployment section. This is a local-first tool for one DJ on one Mac; there
  is nothing to host.

## What is recorded but not fixed

`specs/001-companion-v1/backlog-post-v1.md` is the working list: each item
names what it is, why it was not fixed inside phase 7 or 8, and who owns
closing it. It is deliberately not in `tasks.md`, because the phase machine
refuses to complete a phase while any task there lacks a recorded builder, and
these are follow-on work rather than phase deliverables. Two items involve the
owner's own judgment (B6's keyboard-depth accessibility pass, B7's manual
24×24 target measurement, both dated); the rest are engineering follow-ups
with no external dependency.

## Appendix: what shipped, phase by phase

Drafted by the `scribe` agent from the commit history per this phase's own
routing convention (bulk mechanical text at the cheapest model), reviewed for
accuracy against the actual commits before inclusion here. Full detail and the
"why" behind each decision live in the ADRs (`docs/CONTEXT.md`'s index) and
`specs/001-companion-v1/review-phase-7.md`; this is the "what," not the "why."

### Phase 6 — Implementation, all eight user stories

**Core infrastructure**
- Python 3.12 backend (FastAPI, uvicorn), React 18 + TypeScript frontend
  (Vite), ruff/ESLint/Prettier linting, Makefile build targets, SQLAlchemy 2.x
  with Alembic migrations for the companion's own SQLite store.

**US1 — Spotify sync and matching**
- PKCE OAuth flow and playlist fetch with the 999-track cap short-circuit.
- Matching engine: text normalisation, remix/edit-marker extraction, tiered
  ISRC/exact/fuzzy scoring.
- Golden-set contract test harness, collection reader and in-memory index.

**US2 — Keyboard-first review**
- Sync sessions API, SSE progress stream, keyboard-navigable Review Queue,
  dual local/Spotify playback, completion state.

**US3 — Guarded write path**
- `rb/guard.py` (refusal while Rekordbox runs or the version mismatches),
  `rb/backup.py` (timestamped, verified), `rb/writer.py` (add-only).

**US4 — Missing tracks**
- Missing-track queue, iTunes Search integration for Store Links, audio
  streaming with Range support and an ffmpeg transcode fallback.

**US5 — Collection browser**
- `GET /api/collection` (search, sort, pagination), the `TrackTable` and
  `PlayerBar` components.

**US6 — Genre enrichment**
- MusicBrainz adapter, a resumable incremental runner, the enrichment API and
  panel.

**US7 — Booking structures**
- Booking profile and structure models, tree editing, play-count-ranked
  suggestions, guarded structure Apply.

**Compliance and cross-cutting**
- Full pytest/vitest/Playwright suite, an outbound-host allowlist and `.env`
  permission checks (ASVS), structured JSON logging with credential
  redaction, a full Dutch-copy sweep, an axe-core accessibility sweep (WCAG
  2.2 AA), CI wired to the Playwright suite as a regression guard.

### Phase 7 — Review, the delivered design, and what it found

**Initial two-axis review, 13 blocking findings, all fixed**
- The remix/edit veto only demotes a match, never promotes one (previously it
  could push a track that should have become a Missing Track into Review).
- Migrations now run in `make setup`, closing a fresh-install failure.
- The Review Queue UI was built but never mounted in the app shell; fixed and
  the player token now refreshes rather than going stale.
- `refresh-links` now survives the iTunes rate limit instead of failing the
  whole batch on one row.
- MusicBrainz calls are held to 1 req/s across the whole run, and concurrent
  enrichment runs are refused rather than racing each other.
- The Booking suggestions query was rewritten to scale past SQLite's bound-
  parameter limit.
- `GET /api/collection`'s pagination bounds were closed off, and its database
  connection is now properly closed per request.
- The audio player's diagnostic refetch no longer leaves a second, unread
  transcode running.
- The write-path's own duplicate-track dedup invariant is now pinned by a
  test that can actually fail.

**Delivered shell design, applied across all seven stories**
- The application shell (sidebar, top bar, main pane) from the owner's
  delivered high-fidelity prototype, applied over every existing story rather
  than replacing them.
- The type scale extended to match the prototype's actual sizes (ADR 0020).
- Musical key and label read from Rekordbox into the collection index.

**Second revision: real playlists, real buying, a real backup defect**
- Fixed the actual cause of every real Spotify sync failing: a withheld
  playlist's absent `tracks` object was read as an empty playlist rather than
  an error (later superseded again by the March 2026 endpoint rename below).
- Added a demo mode (`scripts/dev-serve-with-db.py`) that sources tracks from
  Spotify search, for exercising the full pipeline without a fully-opened
  Spotify app.
- FR-041: a Missing Track can be heard and priced before buying it.
- FR-042 and ADR 0022: the Store Link opens in the Music app at the iTunes
  Store view on a Mac, and playback in the buy queue runs through Spotify
  (the source the track came from), not a 30-second store clip.
- Fixed a real write-ahead-log defect: `rb/backup.py` now checkpoints a
  disposable copy of the database before zipping it, so a backup can no
  longer be missing committed transactions that only lived in `master.db-wal`.
- Fixed the sidebar's Rekordbox-library tree, which claimed full treeview
  keyboard semantics (`role="tree"`) without implementing any of them.

### Phase 8 — Delivery

- Fixed Spotify's March 2026 endpoint migration (`/playlists/{id}/tracks` →
  `/playlists/{id}/items`, `tracks`/`track` → `items`/`item`), the actual root
  cause behind what looked like a lingering permissions problem.
- Dropped `claude-fable-5` from the workflow's model pins (cost, not a
  deliberate choice) and widened the usage-limit fallback rule accordingly.
- Reconciled `release` and `main`'s long-diverged histories and promoted
  `release` to `main` (#170, #172).
- This document, `docs/runbook.md`, `scripts/onboarding-wizard.sh`, the ADR
  index and deployment statement in `docs/CONTEXT.md`, and the two ADR
  corrections above (0017 widened, 0021 marked superseded) that phase 8's own
  "no ADR contradicts the code" exit criterion surfaced.
