# Tasks: Rekordbox Companion v1

**Input**: Design documents from `specs/001-companion-v1/` (spec.md, plan.md,
research.md, data-model.md, contracts/api.md, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md — all present.

**Tests**: Included. The constitution's Engineering Baseline mandates TDD per
task and plan.md names the test shape (pytest golden set, fixture-`master.db`
integration, API tests against a fake `rb` adapter, vitest, Playwright); this
is an explicit request, not the template default.

**Organization**: Tasks are grouped by user story (spec.md P1-P7) so each story
is independently implementable and testable, per `docs/process/05-tasks.md`.

**Deliverable type**: `proof-of-value` (specs/PROFILE.md). Cuts from plan.md
are written into the specific tasks they affect, not asserted separately:
Playwright covers only the two value-carrying flows (T033+T052 for
sync→review→apply, T107 for missing→link), player depth stops at
progress+seek (T065), the MusicBrainz adapter is conditional on the R1 spike
(T072), and no task adds optimisation beyond the stated 30s/100ms/40k
numbers.

**Owner-supplied inputs still owed** (grilling D10, `quickstart.md`): fixture
`master.db` + SQLCipher key or decrypted export, `SPOTIFY_CLIENT_ID`,
confirmation of `download-key` on the Mac, audio samples (mp3/m4a/ALAC). None
of these block phase 5 or the start of phase 6; tasks that need them to
*execute* (not to be written) name that dependency explicitly.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps to spec.md user stories US1-US7
- **[complexity: high]**: Escalation flag per `docs/process/workflow.md` model
  routing — cross-cutting change, data migration, tricky concurrency, or a
  security boundary; the reason is carried in the task text. Its absence
  means standard model, by design.

## Path Conventions

Per plan.md's Project Structure: `engine/src/companion/` (Python backend),
`web/src/` (React SPA), `engine/tests/` and `web/tests/`.

---

## Phase 1: Setup

- [x] T001 Create `engine/` package skeleton: `engine/pyproject.toml` (uv-managed,
      Python 3.12), `engine/src/companion/__init__.py`, dependency pins for
      FastAPI, uvicorn, pyrekordbox, rapidfuzz, SQLAlchemy 2.x, Alembic, httpx
- [x] T002 [P] Create `web/` Vite + React 18 + TypeScript project skeleton in
      `web/package.json` and `web/vite.config.ts` (pnpm via corepack), wired to
      the existing `web/design-input/theme.css`
- [x] T003 Configure Python linting/formatting in `engine/pyproject.toml`
      (ruff). Not [P] with T001: same file (gate-review finding).
- [x] T004 [P] Configure TypeScript linting/formatting in `web/eslint.config.js`
      (ESLint 9 flat config — `.eslintrc.cjs` would need ESLint 8, EOL since
      2024, a violation of "prefer boring, well-supported dependencies";
      corrected during phase 6 build, standards-review finding) and
      `web/.prettierrc` (respect existing `.prettierignore`)
- [x] T005 Write `Makefile` targets `setup`, `dev`, `test`, `build`, `run` per
      `specs/001-companion-v1/quickstart.md`
- [x] T006 Write `scripts/dev.sh` launching `uvicorn 127.0.0.1:8787 --reload`
      and the Vite dev proxy together
- [x] T007 [P] Create `engine/tests/fixtures/` with a `matching_golden.yaml`
      schema stub (empty/example cases only — the real ≥50-case set with
      ≥10 hard cases is owner-supplied before phase 6 execution, FR-009,
      SC-003)
- [x] T008 [P] Set up `web/src/api/` client generation: `openapi-typescript` +
      `openapi-fetch`, `pnpm openapi` script per project rule 4 (R5);
      placeholder client until the first OpenAPI schema exists. Commits
      `web/src/api/generated/schema.d.ts` (reversing T002's `.gitignore`
      rule for that path): rule 4 treats the generated client like a
      lockfile, regenerated and re-committed on schema change, not
      regenerated from a live backend on every checkout (spec-review
      finding during phase 6 build).

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T009 Set up SQLAlchemy 2.x engine/session + Alembic migrations framework
      in `engine/src/companion/db/__init__.py` and `engine/src/companion/db/session.py`
- [x] T010 [P] Create `app_config` table and its Alembic migration in
      `engine/src/companion/db/models.py` (data-model.md: paths, pinned
      Rekordbox version, auto-match bar overrides)
- [x] T011 Implement `engine/src/companion/config.py`: paths, env loading,
      pinned version constant `7.2.17` (ADR 0002). Rekordbox install
      detection moved to T012: it requires importing pyrekordbox, which
      project rule 1 confines to `rb/`; `config.py` sits outside `rb/`, so
      the two clauses in this task's original wording were mutually
      exclusive. Corrected during phase 6 build, not silently resolved in
      code.
- [x] T012 Implement `engine/src/companion/rb/reader.py`: collection snapshot,
      playlist/folder tree, play counts, and Rekordbox install/version
      detection (moved from T011) read via pyrekordbox — the only module
      (with its `rb/` siblings) permitted to import pyrekordbox (project
      rule 1)
- [x] T013 Implement `engine/src/companion/rb/index.py`: in-memory collection
      index (`rb_content_id, artist, title, norm_artist, norm_title,
      remix_tokens, duration_ms, bpm, isrc, play_count, location`) rebuilt
      from `reader.py` on demand, serving matching, search and suggestions
      (R6/ADR 0012). `norm_artist`/`norm_title`/`remix_tokens` use a
      placeholder (lowercase/strip, empty tokens) until T024's FR-004
      pipeline exists, since T013 lands in Foundational and T024 lands in
      US1 — the same forward-reference gap T007 already established a
      stub-and-replace precedent for. `index.py` must import from
      `matching/normalize.py` once T024 lands, replacing the placeholder.
- [x] T014 Implement `engine/src/companion/main.py`: FastAPI app factory,
      static SPA mount, binding restricted to `127.0.0.1:8787` (FR-037)
- [x] T015 Implement `GET /api/health` in `engine/src/companion/api/health.py`:
      `{status, rekordbox_version, version_pin_ok, db_path, rekordbox_running,
      ffmpeg_ok}` (contracts/api.md; guard visibility, FR-015). The
      `rekordbox_running` check (`is_rekordbox_running`) lives in
      `rb/reader.py`, not `health.py`, so `rb/guard.py` (T046) reuses the
      same implementation instead of a second one that could disagree with
      it — doesn't need pyrekordbox, but rb/ already owns "facts about the
      Rekordbox process" (T012). contracts/api.md doesn't enumerate
      `status`'s values: implemented as `"ok"` when Rekordbox is installed
      and matches the pinned version, else `"degraded"`, directly from the
      spec's own edge case wording ("the app starts in a degraded state...
      instead of erroring per screen") rather than a fresh invention.
- [x] T016 [P] Implement `POST /api/collection/reindex` in
      `engine/src/companion/api/collection.py` wrapping the `rb/index.py`
      rebuild
- [x] T101 Implement `GET /api/playlists` (read-only Rekordbox
      playlist/folder tree, `rb/reader.py`) and `GET/PUT /api/config`
      (paths, thresholds, `app_config` table from T010) in
      `engine/src/companion/api/collection.py` and
      `engine/src/companion/api/config.py` (contracts/api.md). Gate-review
      finding: these two contract endpoints had no task. Not [P] with T016:
      shares `api/collection.py`, and depends on T010. contracts/api.md's
      "tree" wording for `GET /api/playlists` was clarified to `[PlaylistNode]`
      (flat, `parent_id`-linked): that has always been `read_playlist_tree`'s
      shape (T012), the endpoint just exposes it as-is; `PUT /api/config`'s
      "same" was clarified to mean it echoes the whole table, not only the
      changed keys (build-time review finding, not a behaviour change).
- [x] T108 [P] Test in `engine/tests/rb/test_reader.py`: `reader.py` returns
      the documented fields (artist, title, duration, BPM, play count,
      location) from the fixture `master.db` collection snapshot and
      playlist/folder tree. Satisfied by T012's own test suite in that same
      file (against a duck-typed fake, not the real fixture — owner-supplied
      fixture still owed, quickstart.md); no separate task needed.
- [x] T109 [P] Test in `engine/tests/rb/test_index.py`: the in-memory index
      rebuild reflects `reader.py` output, including the normalised
      artist/title and remix-token fields matching consumes (R6/ADR 0012).
      Gate-review finding: Foundational tasks had no test coverage, unlike
      every story phase. Satisfied by T013's own test suite in that same
      file (against the T013 placeholder normalisation, not T024's real
      FR-004 pipeline yet); no separate task needed.
- [x] T017 [P] Wire `web/src/theme/index.css` to consume
      `web/design-input/theme.css` as the Tailwind v4 `@theme`; no hardcoded
      colour/typography/spacing/radius values anywhere downstream (project
      rule 5). Only the `latin` Inter unicode-range subset is aliased under
      the SpotifyMixUI/SpotifyMixUITitle token names; Dutch UI copy (FR-038)
      is fully covered, but Collection track/artist data with Eastern
      European, Turkish, Cyrillic or Greek characters would fall through to
      a system-font fallback once US5 renders real track names — deferred,
      not fixed here (gate-review finding).
- [x] T018 [P] Set up structured logging in `engine/src/companion/logging.py`
      with token/key redaction as a tested formatter property (NIS2 logging
      plan) [complexity: high] — security boundary: a missed redaction path
      would leak the operator's Spotify tokens or the SQLCipher key into logs

**Checkpoint**: Foundation ready — user story implementation can begin.

---

## Phase 3: User Story 1 - Instant match report for a Spotify playlist (Priority: P1) 🎯 MVP

**Goal**: Paste a Spotify playlist URL, get every track classified matched /
review / missing with totals, within 30s for 100 tracks.

**Independent Test**: Golden-set + fixture Collection classification, no
write path or review UI required (spec.md).

### Tests for User Story 1

- [x] T019 [P] [US1] Golden-set contract test harness in
      `engine/tests/test_matching_golden.py` loading
      `engine/tests/fixtures/matching_golden.yaml`; asserts 100% pass and that
      the set only ever grows (FR-009). Real fixture data is owner-supplied
      before this can execute against real cases (quickstart.md); the harness
      itself is not blocked.
- [x] T020 [P] [US1] Unit tests for normalisation + remix-token extraction in
      `engine/tests/matching/test_normalize.py` (FR-004)
- [x] T021 [P] [US1] Unit tests for tiered scoring/classification in
      `engine/tests/matching/test_engine.py`: ISRC fast lane, exact+duration
      fast lane, 92/75 score bars, 40/60 artist/title weighting, duration
      penalty beyond 5s, remix-marker veto (FR-005..FR-008)
- [x] T022 [P] [US1] API contract test for `POST /api/sync/sessions` against a
      fake `rb` adapter in `engine/tests/api/test_sync_sessions.py`: exactly
      one status per track (FR-003), 999-track cap refused before the session
      starts (edge case), duplicate playlist positions reported once each
      (edge case)
- [x] T023 [P] [US1] Vitest for the match report table in
      `web/tests/features/spotify-sync/MatchReport.test.tsx`: totals and
      per-track status conveyed in text, not colour alone (WCAG)
- [x] T097 [P] [US1] Performance test in
      `engine/tests/perf/test_match_report.py`: a 100-track playlist against
      the 40.000-entry index produces a complete match report in under 30
      seconds (SC-001); a 999-track playlist (the cap, D12) completes within
      5 minutes (plan.md constraint-to-decision map). Gate-review finding B3.
- [x] T104 [US1] Test in `engine/tests/api/test_sync_sessions.py`: a
      Spotify session expiring mid Sync Session fails the session with a
      re-connect prompt and no partial report is presented as complete
      (edge case). Not [P] with T022: same file (gate-review finding).
- [x] T105 [P] [US1] Test in `engine/tests/api/test_health.py`: when
      `master.db` is not at the expected path, the app starts in a degraded
      state naming the expected path and blocking Rekordbox-backed features
      instead of erroring per screen (edge case)

### Implementation for User Story 1

- [x] T024 [US1] Implement `engine/src/companion/matching/normalize.py`:
      case-insensitive normalisation, featuring/remaster/bracket/punctuation/
      diacritic stripping, remix/edit marker kept as a distinct token (FR-004)
- [x] T025 [US1] Implement `engine/src/companion/matching/engine.py`: ISRC
      exact-match lane (FR-005), exact-normalised+≤3s-duration lane (FR-006),
      fuzzy scoring 40% artist / 60% title with duration penalty beyond 5s and
      the 92/75 bars (FR-007), remix-marker veto forcing Review Queue
      regardless of score (FR-008)
- [x] T026 [US1] Implement `engine/src/companion/integrations/spotify.py`:
      OAuth PKCE login/callback/status/disconnect, playlist fetch with
      pagination, 999-track cap enforced before the session starts (edge
      case) [complexity: high] — security boundary: exchanges and stores the
      operator's Spotify credentials. T022 review finding: T022's contract
      test only checks the end-effect refusal (422, nothing persisted) at
      the `api/sync.py` router seam, against a fake that already returns all
      tracks in one call — it does not exercise pagination stopping early
      once the cap is exceeded. This task's own build must short-circuit
      pagination itself (the reason tasks.md puts the cap here rather than
      in the router) and should add its own unit test for that, since no
      other task in tasks.md covers it.
- [x] T027 [US1] Add `playlist_link`, `sync_session`, `sync_track` models and
      Alembic migration in `engine/src/companion/db/models.py` (data-model.md).
      `playlist_link` moved here from T049 (build finding): `sync_session`
      FKs into it, and T028 needs it for FR-010's lineage reuse, both before
      US3 exists.
- [x] T028 [US1] Implement `POST /api/sync/sessions` in
      `engine/src/companion/api/sync.py`: fetch playlist, run the matching
      engine, persist `sync_track` rows with status and top-3 candidates,
      classify local/unavailable tracks as `unmatchable` (edge case)
- [x] T029 [US1] Implement `GET /api/sync/sessions` and
      `GET /api/sync/sessions/{id}` in `engine/src/companion/api/sync.py`.
      Not [P] with T028: same file (gate-review finding).
- [x] T030 [US1] Implement the `sync_progress` SSE event on `GET /api/events`
      in `engine/src/companion/api/events.py` for the fetch+match run (R4)
- [x] T031 [P] [US1] Build `web/src/features/spotify-sync/PlaylistUrlForm.tsx`:
      URL input with field-naming validation errors for invalid/private/
      unreachable playlists (WCAG, edge case)
- [x] T102 [P] [US1] Build `web/src/features/spotify-sync/SpotifyConnection.tsx`:
      connection status, connect action, disconnect action — the AVG
      deletion path (FR-001, pii-inventory.md). Gate-review finding: FR-001
      had no frontend task.
- [x] T032 [US1] Build `web/src/features/spotify-sync/MatchReport.tsx`:
      per-track status and totals, keyboard-operable, focus always visible,
      AA contrast, 24x24 targets (WCAG acceptance criteria, US1). Build
      finding: no task in this decomposition wires any feature component
      into `web/src/App.tsx` -- every US builds isolated
      `web/src/features/<name>/*.tsx` files with nothing assembling them
      into a reachable page, yet T033 (next) needs a real page to click
      through. This task also does that minimal wiring for US1 only
      (`PlaylistUrlForm` -> `MatchReport`, plus `SpotifyConnection`, T031/
      T102): no router, no nav framework -- premature before a second user
      story's UI exists. A real app shell/navigation is a Polish-phase gap
      (T093's "seam deltas" or a future gate-review finding), flagged here
      rather than silently absorbed into one task's scope.
- [x] T033 [US1] Playwright smoke e2e in `web/tests/e2e/sync-review-apply.spec.ts`
      covering the paste-URL→report-renders slice of the sync→review→apply
      flow (one of the two flows in the proof-of-value e2e budget, plan.md).
      Build finding: `App.tsx` (T032) renders `PlaylistUrlForm`
      unconditionally, not gated on `SpotifyConnection`'s connected state --
      submitting while disconnected instead surfaces `PlaylistUrlForm`'s
      existing `spotify_not_connected` error message. Accepted as-is (a
      simpler design than a conditional gate, and still spec-compliant: the
      DJ gets a clear, field-naming error either way), not changed here;
      recorded so it reads as an intentional choice, not a rediscovered gap.

**Checkpoint**: US1 independently functional and testable (real-data
execution still needs the owner's fixture `master.db` and golden set).

---

## Phase 4: User Story 2 - Keyboard-first review of doubtful matches (Priority: P2)

**Goal**: Resolve the Review Queue entirely by keyboard, hearing both the
local candidate and the full Spotify original.

**Independent Test**: Seeded Review Queue resolved to accepted/rejected using
only documented keys; both audio sources playable per item (spec.md).

- [x] T099 [US2] Implement `GET /api/auth/spotify/player-token` in
      `engine/src/companion/integrations/spotify.py`: short-lived token for
      the Web Playback SDK (contracts/api.md "Spotify auth"). Must land
      before T034 can run despite the higher ID — the spike depends on it.
      Gate-review finding: the endpoint T034/T040 depend on had no task.
- [x] T034 [US2] R2 spike in `web/src/features/review/spotify-playback-spike.tsx`:
      Spotify Web Playback SDK connect + play one full track on `127.0.0.1`
      from a throwaway page, using T099's player token; record pass/fail. On
      failure, fall back to local preview + a `spotify:track:` deep link and
      amend ADR 0009 (research.md R2, unknown #3). Owner decision
      2026-08-18: the exploratory throwaway spike is skipped -- this dev
      container has no real Spotify Premium account, no real browser with
      Widevine/EME, and no guaranteed network path to Spotify's CDN, so no
      pass/fail here would be genuine evidence either way. Owner committed
      directly to the SDK-embedded approach (ADR 0009 stands, unchanged, not
      amended to the fallback); T040 builds `DualPlayback.tsx` straight
      against the Web Playback SDK using T099's player-token endpoint, with
      real playback verification left to the owner's Mac (same pattern as
      T089/quickstart.md's owner-supplied-fixture tasks) rather than
      simulated here.

### Tests for User Story 2

- [x] T035 [P] [US2] Vitest for Review Queue keyboard handling in
      `web/tests/features/review/ReviewQueue.test.tsx`: arrows navigate, A
      accepts, R rejects, space previews (FR-011)
- [x] T036 [P] [US2] API contract tests in
      `engine/tests/api/test_sync_review.py`: reject spawns a Missing Track
      (FR-012), accept/reject persist immediately (FR-014)

### Implementation for User Story 2

- [x] T037 [US2] Implement
      `POST /api/sync/sessions/{id}/tracks/{tid}/accept` and
      `.../reject` in `engine/src/companion/api/sync.py`, persisting the
      resolution immediately (FR-014). Build finding: reject must spawn a
      real `missing_track` row (FR-012; T036 tests this; T058 already says
      "reject→missing_track spawn (from US2, T037)") -- but `missing_track`
      was originally modelled in T056 (US4), scheduled well after this task.
      `missing_track` model + Alembic migration move here, ahead of T056,
      the same playlist_link-ahead-of-T049 pattern from T027.
- [x] T038 [US2] Implement `engine/src/companion/audio/stream.py`:
      `GET /api/player/stream/{rb_content_id}` with HTTP Range support for
      local candidate preview, path resolved only from `rb_content_id`
      (ASVS V6/V12) [complexity: high] — security boundary: the stream path
      must never accept a client-supplied file path, only the id lookup
- [x] T039 [US2] Build `web/src/features/review/ReviewQueue.tsx`: arrows/A/R/
      space wiring, focus never lost on resolve, candidates and scores in
      text (FR-011, WCAG)
- [x] T040 [US2] Build `web/src/features/review/DualPlayback.tsx`: local
      candidate via `stream.py`, Spotify original via the Web Playback SDK
      (T099 token, or T034's fallback), playing/paused exposed to assistive
      tech (FR-013, WCAG)
- [x] T041 [P] [US2] Build `web/src/features/review/QueueComplete.tsx`:
      completion state with updated session totals when the queue empties
- [x] T100 [P] [US2] Build `web/src/components/KeymapOverlay.tsx`: an
      on-screen, discoverable key map (arrows, A, R, space) satisfying US2's
      WCAG criterion that the key map is discoverable from the screen, not
      only documented externally (spec.md US2 accessibility criteria;
      plan.md Project Structure already names this component). Gate-review
      finding: this WCAG criterion had no task.

**Checkpoint**: US1+US2 independently functional.

---

## Phase 5: User Story 3 - Apply matches to Rekordbox, guarded (Priority: P3)

**Goal**: One guarded action writes accepted Matches into Rekordbox as a
playlist, backed up and readback-verified, add-only on re-apply.

**Independent Test**: Against fixture `master.db`: apply writes the expected
playlist, a backup exists per write, readback confirms content, a second
apply adds only new tracks, refusals fire when guard conditions fail
(spec.md).

- [x] T042 [US3] R3 spike in `engine/tests/spikes/rb_write_smoke.py`:
      pyrekordbox write smoke test against fixture `master.db` — create
      playlist, create folder, add tracks, readback, verify the database
      still opens cleanly [complexity: high] — security boundary: gates
      every subsequent write to the DJ's irreplaceable library; failure stops
      phase 6 and reopens phase 4 (research.md R3, unknown #1)

### Tests for User Story 3

- [x] T043 [P] [US3] Integration tests in
      `engine/tests/rb/test_writer_integration.py` against fixture
      `master.db`: backup created before write, readback verifies every
      accepted match present, a second apply after re-sync adds only new
      tracks (add-only, ADR 0006)
- [x] T044 [P] [US3] Contract tests in `engine/tests/api/test_sync_apply.py`
      for the three refusal codes (`rekordbox_running`, `version_mismatch`,
      `insufficient_disk`) naming the fix (409, scenarios 2-3, edge case)
- [x] T045 [US3] Test in `engine/tests/rb/test_writer_integration.py` that
      a Target Playlist deleted inside Rekordbox is detected and recreated on
      the next Apply, reported to the DJ (FR-019, scenario 5). Not [P] with
      T043: same file (gate-review finding).
- [x] T096 [US3] Contract and integration tests for the two remaining
      apply failure paths, in `engine/tests/api/test_sync_apply.py` and
      `engine/tests/rb/test_writer_integration.py`: a backup that fails
      verification blocks the write and returns `backup_failed` (409, same
      as the other guard refusals, constraints.md Retention); a write whose
      readback verification fails reports which Backup to restore and does
      not mark the session applied (scenario 7). Not [P] with T043-T045:
      shares both files. Gate-review finding.
- [x] T106 [US3] Test in `engine/tests/api/test_sync_apply.py`: a playlist
      containing the same track twice is reported once per playlist
      position (already covered by T022) but Apply writes it to the Target
      Playlist exactly once (edge case, de-duplication on write)

### Implementation for User Story 3

- [x] T046 [US3] Implement `engine/src/companion/rb/guard.py`: running-check,
      version-pin (7.2.17) check, disk-headroom check, refusing any write
      before it starts (FR-015) [complexity: high] — security boundary: the
      sole gate protecting the irreplaceable Rekordbox library from a bad
      write. If this file imports pyrekordbox directly rather than only
      calling into `rb/reader.py`, it must also `import companion.rb.reader`
      (even if otherwise unused) so T018's `configure_logging()` import-time
      side effect runs before pyrekordbox does — nothing enforces rule 1's
      "pyrekordbox confined to rb/" mechanically, so the ordering guarantee
      currently holds by convention only (T018 final-review finding).
- [x] T047 [US3] Implement `engine/src/companion/rb/backup.py`: timestamped
      zipped Backup, verify readability, prune beyond newest 10 only after a
      verified create (ADR 0016). Standard, not high: the destructive prune
      step only ever runs after a verified create, which bounds the risk
      that guard.py/writer.py carry directly (gate-review finding, recorded
      rather than silently omitted).
- [x] T048 [US3] Implement `engine/src/companion/rb/writer.py`: guarded
      playlist/folder writes, add-only updates, readback verification; never
      edits metadata/cues/beat grids, never deletes or reorders anything it
      did not create (FR-016..FR-018, Principle II/III) [complexity: high] —
      cross-cutting security boundary: the sole write path into `master.db`,
      shared by US3 and US7 (T086). Same T018 ordering note as T046: ensure
      `configure_logging()` has run before this module uses pyrekordbox.
- [x] T049 [US3] Add `write_log` model and Alembic migration in
      `engine/src/companion/db/models.py`; audits every write (SC-006).
      `playlist_link` moved to T027 (T027 build finding): `sync_session`
      needs `playlist_link_id` for FR-010's "re-use one Sync Session lineage
      per Spotify playlist URL", which T028 (US1, `POST /api/sync/sessions`)
      must satisfy — that's before US3 exists, so `playlist_link` cannot wait
      for T049.
- [x] T050 [US3] Implement `POST /api/sync/sessions/{id}/apply` in
      `engine/src/companion/api/sync.py`: guard → backup → write → readback →
      `write_log` row → `ApplyResult`, emitting the `apply_done` SSE event on
      `/api/events` on completion (contracts/api.md, R4)
- [x] T051 [P] [US3] Build `web/src/features/spotify-sync/ApplyAction.tsx`:
      confirmation dialog, result state, refusal/failure messages naming the
      blocking condition and the fix, keyboard-operable (WCAG)
- [ ] T052 [US3] Extend `web/tests/e2e/sync-review-apply.spec.ts` (T033) to
      cover apply against the fixture `master.db`, completing the first of
      the two proof-of-value e2e flows

**Checkpoint**: US1-US3 independently functional; the guarded write path
(reused by US7) exists.

---

## Phase 6: User Story 4 - Missing tracks become purchases (Priority: P4)

**Goal**: Every unmatched track gets a Store Link and a trackable status;
acquired tracks leave the queue on re-sync.

**Independent Test**: Seeded missing queue: NL storefront links resolve,
statuses persist, an acquired track leaves the queue on re-sync (spec.md).

### Tests for User Story 4

- [ ] T053 [P] [US4] Contract test in `engine/tests/api/test_missing.py`: at
      least 90% of a 20-track test set resolve to the correct NL store page
      (SC-004)
- [ ] T054 [US4] Test in `engine/tests/api/test_missing.py`: `ignored` is
      sticky across re-syncs of the same playlist (scenario 3); a re-synced
      acquired track auto-closes (FR-023). Not [P] with T053: same file
      (gate-review finding).

### Implementation for User Story 4

- [ ] T055 [US4] Implement `engine/src/companion/integrations/itunes.py`:
      iTunes Search API lookup, `country=NL`, outbound restricted to
      `itunes.apple.com` (ASVS V10/V14 SSRF)
- [x] T056 [US4] Add `missing_track` model (UNIQUE per `sync_track`) and
      Alembic migration in `engine/src/companion/db/models.py`. Moved to
      T037 (build finding): `missing_track` is needed the moment reject
      spawns one (FR-012, US2), before US4 exists.
- [ ] T057 [US4] Implement `GET /api/missing`,
      `POST /api/missing/{id}/status`, `POST /api/missing/{id}/link`,
      `POST /api/missing/refresh-links` in `engine/src/companion/api/missing.py`
- [ ] T058 [US4] Wire FR-023 auto-close: reject→missing_track spawn (from
      US2, T037) and re-sync match transition back to `matched` in
      `engine/src/companion/api/sync.py`
- [ ] T059 [P] [US4] Build `web/src/features/missing/MissingQueue.tsx`: Store
      Link + copy action, status controls, manual override input with
      field-naming errors (WCAG)
- [ ] T107 [US4] Playwright smoke e2e in `web/tests/e2e/missing-link.spec.ts`
      covering the missing→link flow: a completed sync with Missing Tracks
      shows the queue, a Store Link resolves and copies (second of the two
      proof-of-value e2e flows, plan.md). Gate-review finding: this flow was
      referenced by T095 but no task ever authored it.

**Checkpoint**: US1-US4 independently functional.

---

## Phase 7: User Story 5 - Browse and play the Collection (Priority: P5)

**Goal**: Search, sort and play the 30.000+ track Collection in the browser.

**Independent Test**: Against a fixture Collection: search returns expected
tracks fast, native formats play, conversion fallback passes on a non-native
fixture file (spec.md).

### Tests for User Story 5

- [ ] T060 [P] [US5] Perf test in `engine/tests/test_collection_perf.py`:
      `/api/collection` search responds <100ms/keystroke at 40.000 indexed
      tracks (SC-005; tested above the 30k target per constraints)
- [ ] T061 [P] [US5] Test in `engine/tests/audio/test_stream.py`: a missing or
      unreadable audio file reports `file_missing` instead of failing
      silently (FR-026)

### Implementation for User Story 5

- [ ] T062 [US5] Implement `GET /api/collection` in
      `engine/src/companion/api/collection.py`: query/sort/limit/offset over
      the in-memory index (T013), sort by artist/title/BPM/Play Count
- [ ] T063 [US5] Extend `engine/src/companion/audio/stream.py` (T038) with
      the ffmpeg pipe fallback for non-native formats (ALAC fixture) — no
      waveform, no gapless, no preload (proof-of-value cut, plan.md)
      [complexity: high] — tricky concurrency: Range/seek requests
      interleaved with the ffmpeg subprocess pipe must not deadlock or
      corrupt partial reads. Gate-review finding: this risk was originally
      flagged on T038, which doesn't build the pipe; moved to the task that
      actually implements it.
- [ ] T064 [P] [US5] Build `web/src/components/TrackTable.tsx`: searchable,
      sortable table, keyboard navigation, AA contrast at dense layout (WCAG)
- [ ] T065 [P] [US5] Build `web/src/components/PlayerBar.tsx`: progress bar +
      seek only, playing/paused/seek state exposed to assistive tech (WCAG;
      proof-of-value cut: no waveform, per plan.md)

**Checkpoint**: US1-US5 independently functional.

---

## Phase 8: User Story 6 - Enriched genres with manual override (Priority: P6)

**Goal**: Assign Enriched Genres from external sources, app-side only, with a
permanent manual override.

**Independent Test**: Enrich a fixture Collection, measure coverage, exercise
manual override, confirm `master.db` bytes unchanged after (spec.md).

- [ ] T066 [US6] R1 spike in `engine/scripts/enrichment_coverage_spike.py`:
      run the Spotify-genres and MusicBrainz adapters over the fixture
      collection, report coverage % and a 50-track sample for owner judgement
      against SC-008 (≥80% coverage, ≥90% sample quality). If Spotify-genres-
      only clears SC-008, defer the MusicBrainz adapter behind its seam
      rather than build it (proof-of-value cut, plan.md; research.md R1,
      unknown #2)

### Tests for User Story 6

- [ ] T067 [P] [US6] Test in `engine/tests/enrichment/test_source.py`: a
      manual genre override is never overwritten by a later enrichment run
      (FR-028)
- [ ] T068 [P] [US6] Test in `engine/tests/enrichment/test_runner.py`: an
      enrichment run leaves `master.db` byte-for-byte unchanged (FR-030,
      Principle III)
- [ ] T069 [US6] Test in `engine/tests/enrichment/test_runner.py`: an
      interrupted enrichment run resumes without redoing done tracks
      (ADR 0013). Not [P] with T068: same file (gate-review finding).

### Implementation for User Story 6

- [ ] T070 [US6] Implement `engine/src/companion/enrichment/source.py`:
      `GenreSource` seam (ADR 0013)
- [ ] T071 [P] [US6] Implement `engine/src/companion/enrichment/spotify_genres.py`
      adapter
- [ ] T072 [P] [US6] Implement `engine/src/companion/enrichment/musicbrainz.py`
      adapter at 1 req/s, only if T066's spike keeps it in scope
      (proof-of-value cut, plan.md)
- [ ] T073 [US6] Implement `engine/src/companion/enrichment/runner.py`:
      incremental, resumable queue over `enrichment_state` (data-model.md)
- [ ] T074 [US6] Add `enriched_genre`, `enrichment_state` models and Alembic
      migration in `engine/src/companion/db/models.py`
- [ ] T075 [US6] Implement `POST /api/enrichment/run`,
      `GET /api/enrichment/status`, `GET /api/enrichment/unenriched`,
      `PUT /api/collection/{rb_content_id}/genres` (manual override wins
      forever, FR-028) in `engine/src/companion/api/enrichment.py`
- [ ] T076 [US6] Implement the `enrichment_progress` SSE event on
      `GET /api/events` (R4)
- [ ] T077 [P] [US6] Build `web/src/features/enrichment/EnrichmentPanel.tsx`:
      coverage status, unenriched work list, manual genre editor with
      field-naming errors, manual/automatic origin conveyed in text not
      colour (WCAG)

**Checkpoint**: US1-US6 independently functional.

---

## Phase 9: User Story 7 - Hand-designed booking structures with curated suggestions (Priority: P7)

**Goal**: Design a folder/playlist tree, curate ranked Suggestions per
playlist, apply the whole structure through the guarded write path.

**Independent Test**: Against a fixture Collection with seeded Enriched
Genres: suggestions honour profile filters and Play Count rank, curation is
editable, apply writes the expected tree (spec.md).

**Dependency note**: this story requires US6's Enriched Genres to filter
Suggestions meaningfully (spec.md: "hard prerequisite for User Story 7") and
reuses US3's guard/backup/writer (T046-T048) rather than rebuilding them —
the one documented exception to story independence in this feature.

### Tests for User Story 7

- [ ] T078 [P] [US7] Test in `engine/tests/bookings/test_suggestions.py`:
      suggestions honour a profile's genre tags and BPM filters, rank by Play
      Count descending, exclude tracks with missing BPM from BPM filters
      while reporting the excluded count (edge case)
- [ ] T079 [P] [US7] Test in `engine/tests/bookings/test_structures.py`:
      dismissed suggestions never return for that playlist (FR-034); a node
      already applied to Rekordbox is rename-locked (FR-032, edge case)
- [ ] T080 [P] [US7] Integration test in
      `engine/tests/bookings/test_structure_apply.py`: apply writes the full
      folder/playlist tree to fixture `master.db` through the same guard/
      backup/readback path as US3; re-apply after edits is add-only
      (FR-018, scenario 6)

### Implementation for User Story 7

- [ ] T081 [US7] Add `booking_profile`, `booking_profile_genre_tag`,
      `structure`, `structure_node`, `structure_track`,
      `suggestion_dismissal` models and Alembic migration in
      `engine/src/companion/db/models.py`, seeded profiles (horeca,
      bruiloft, prive, thema, FR-031)
- [ ] T082 [P] [US7] Implement `GET/POST /api/profiles`,
      `PUT/DELETE /api/profiles/{id}` in `engine/src/companion/api/profiles.py`
      (FR-031)
- [ ] T083 [US7] Implement `engine/src/companion/bookings/models.py`:
      suggestions query — filter index (T013) by profile genre tags against
      `enriched_genre` and BPM, rank by play count, subtract
      `structure_track` and `suggestion_dismissal` rows (FR-033, replaces the
      old generator per ADR 0008)
- [ ] T084 [US7] Implement `GET/POST /api/structures`,
      `PUT/DELETE /api/structures/{id}`,
      `POST/PUT/DELETE /api/structures/{id}/nodes` in
      `engine/src/companion/api/structures.py` (tree editing, FR-032,
      rename-lock on applied nodes)
- [ ] T085 [US7] Implement
      `GET /api/structures/{id}/nodes/{nid}/suggestions`,
      `POST .../tracks`, `DELETE .../tracks/{rb_content_id}`,
      `POST .../dismissals` in `engine/src/companion/api/structures.py`
      (FR-033, FR-034). Not [P] with T084/T086: same file (gate-review
      finding).
- [ ] T086 [US7] Implement `POST /api/structures/{id}/apply` in
      `engine/src/companion/api/structures.py`, reusing `rb/writer.py` +
      `rb/guard.py` + `rb/backup.py` from US3 (T046-T048); per-node
      `ApplyResult`, add-only re-apply, emitting `apply_done` on
      `/api/events` (FR-018, FR-035, R4)
- [ ] T087 [P] [US7] Build `web/src/components/Tree.tsx`: folder/playlist
      tree editor (create/rename/nest/move/delete), Set Phase labels,
      Run-of-Show folder, keyboard-operable (WCAG)
- [ ] T088 [P] [US7] Build `web/src/features/bookings/BookingWorkspace.tsx`:
      profile editor, suggestion list (accept/dismiss, already-in-playlist
      flag), apply action and result state, naming-error inputs (WCAG)

**Checkpoint**: All seven user stories independently functional.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T089 [P] Run `specs/001-companion-v1/quickstart.md` validation scenarios
      end to end once owner inputs (fixture `master.db` + key,
      `SPOTIFY_CLIENT_ID`, audio samples) land — blocked on the owner, not on
      this decomposition (grilling D10)
- [ ] T090 [P] ASVS-mapped security pass in
      `engine/tests/security/test_asvs_boundaries.py`: outbound HTTP
      allowlist enforcement (`api.spotify.com`, `itunes.apple.com`,
      `musicbrainz.org` only; ASVS V10/V14 SSRF), `.env`/token file
      permission check (ASVS V6/V12)
- [ ] T091 [P] Accessibility sweep in `web/tests/e2e/accessibility.spec.ts`
      across all seven stories: keyboard-only pass, focus visibility, AA
      contrast, 24x24 targets, form-error announcements (WCAG 2.2 AA, phase 7
      review checklist input)
- [ ] T092 Test in `engine/tests/api/test_readonly_during_run.py`: read-only
      features (collection browse, playback) stay usable while a Sync
      Session or enrichment run is in progress (FR-040, edge case)
- [ ] T093 [P] Update `docs/architecture.md` with any seam deltas discovered
      during build, keeping it in sync with plan.md's seam list
- [ ] T094 Verify `engine/tests/fixtures/matching_golden.yaml` holds ≥50
      cases with ≥10 hard cases and passes at 100% (SC-003) — execution
      depends on the owner-supplied real cases; this task records the gate
- [ ] T095 [P] Run the Playwright suite
      (`web/tests/e2e/sync-review-apply.spec.ts`,
      `web/tests/e2e/missing-link.spec.ts` from T107) as the CI-facing
      regression guard for the two core flows (proof-of-value e2e budget,
      plan.md)
- [ ] T098 [P] Verify all user-facing SPA copy is Dutch (FR-038) across every
      component in `web/src/features/` and `web/src/components/`: labels,
      button text, empty states, toasts and error messages; only `code`
      values in API errors and code identifiers stay English (contracts/api.md
      convention). Gate-review finding B1.
- [ ] T103 [P] Record the owner's SC-009 judgement (booking-prep time under
      30 minutes where it took hours) on the first real booking prepared
      with the app; a manual sign-off, not a code deliverable — log the
      outcome in `docs/CONTEXT.md`. Gate-review finding: SC-009 had no
      recorded validation step.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all user stories.
- **User Stories (Phase 3-9)**: all depend on Foundational. Within that, most
  are independent (see exceptions below) and may proceed in priority order or
  in parallel if staffed.
- **Polish (Phase 10)**: depends on all seven stories being complete (or, for
  T089/T094, on owner-supplied data landing).

### User Story Dependencies (exceptions to independence)

- **US2** (T038, `audio/stream.py`) is extended, not duplicated, by **US5**
  (T063).
- **US2**'s T099 (`GET /api/auth/spotify/player-token`) extends **US1**'s
  T026 `integrations/spotify.py` rather than creating a new file
  (gate-review finding).
- **US3** (T046-T048, guard/backup/writer) is reused, not duplicated, by
  **US7** (T086) — the guarded write path is built once.
- **US7** requires **US6**'s Enriched Genres to filter Suggestions
  meaningfully (spec.md: "hard prerequisite"); it can be scaffolded earlier
  but only produces real Suggestions once US6 has run.
- All other stories (US1, US2, US4, US5) are independently testable per
  spec.md's own Independent Test criteria.

### Within Each User Story

- Tests are written first and must fail before implementation (constitution
  Engineering Baseline, TDD).
- Models/migrations before services; services before endpoints; backend
  before the frontend feature that consumes it.
- Story complete (checkpoint) before moving to the next priority, unless
  staffed in parallel.

### Parallel Opportunities

- All Setup tasks marked [P] run in parallel.
- All Foundational tasks marked [P] run in parallel once T009/T011/T012 (the
  sequential prerequisites within Phase 2) land.
- Once Foundational completes, US1 and US4 can start in parallel; US2 can
  start in parallel too, but its T099 depends on US1's T026 landing first
  (both extend `integrations/spotify.py`); US5 can start in parallel, but
  its T063 depends on US2's T038 landing first (both extend
  `audio/stream.py`, gate-review finding — this contradicted an earlier
  version of this line); US3 should land before US7's apply step; US6
  should land before US7 produces real suggestions.
- Within a story, all [P] test tasks run together; all [P] model/component
  tasks run together.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Golden-set contract test harness in engine/tests/test_matching_golden.py"
Task: "Unit tests for normalisation in engine/tests/matching/test_normalize.py"
Task: "Unit tests for scoring/classification in engine/tests/matching/test_engine.py"
Task: "API contract test for POST /api/sync/sessions in engine/tests/api/test_sync_sessions.py"
Task: "Vitest for the match report table in web/tests/features/spotify-sync/MatchReport.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (blocks all stories).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run US1's Independent Test (needs the owner's
   fixture `master.db` and golden set to exercise real data; the harness and
   UI are testable against a fake `rb` adapter without them).

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → validate → MVP.
3. US2 → validate (needs the R2 spike result, T034).
4. US3 → validate (needs the R3 spike result, T042, and gates phase 6 on
   failure).
5. US4 → validate.
6. US5 → validate.
7. US6 → validate (needs the R1 spike result, T066).
8. US7 → validate (needs US6's genres and US3's write path).
9. Polish (Phase 10), gated on owner-supplied inputs for full-data runs.

---

## Notes

- `[P]` tasks touch different files with no dependency on an incomplete task.
- `[Story]` traces every phase-3-9 task back to its spec.md user story.
- Every task carries its own acceptance criteria (FR/SC/scenario reference)
  so implementation doesn't require re-reading the spec.
- Commit after each task or logical group, per the constitution's atomic-
  commit baseline; two-axis review (`mattpocock-skills:code-review`) runs per
  task in phase 6, one skill and one commit at a time, not one review at the
  end.
- Three spikes (T034 R2, T042 R3, T066 R1) are placed at the start of the
  story they gate, not in Foundational, because none of them block *every*
  story — only R3 (T042) can reopen phase 4 on failure.
