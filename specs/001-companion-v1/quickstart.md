# Quickstart & Validation: Rekordbox Companion v1

Phase 1 output of `/speckit-plan`, 2026-08-16. How to run the app and prove
each user story end to end. Implementation detail lives in `tasks.md` and the
code; this is the validation script.

## Prerequisites

- uv, pnpm (via corepack), ffmpeg in the container image (already present).
- Owner-supplied inputs (grilling D10, still owed before phase 6 starts):
  - fixture copy of `master.db` at `engine/tests/fixtures/master.db` (never
    committed, rule 3), delivered together with its SQLCipher key or as a
    decrypted export — without one of those the fixture is unreadable and the
    R3 spike cannot start (phase 4 grilling, finding 1);
  - Spotify Developer client id in `.env` (`SPOTIFY_CLIENT_ID`);
  - confirmation that `python -m pyrekordbox download-key` succeeded on the
    Mac (the production key stays on the Mac).
- A handful of mp3/m4a sample files plus one ALAC file for the transcode test
  (fixtures, not real library files).

## Run

```bash
make setup   # uv sync + alembic upgrade head + pnpm install + hooks
make dev     # uvicorn 127.0.0.1:8787 --reload + vite dev proxy
make test    # pytest + vitest
make build && make run   # production mode: SPA served by FastAPI
```

`make setup` applies every Alembic migration to `data/app.sqlite` (created if
absent), so `make dev`/`make run` always start against an up-to-date schema.
Re-run `make setup` (or, from `engine/`, `uv run alembic upgrade head`
directly) after pulling changes that add a new migration.

`/api/health` must report `version_pin_ok: true` against the fixture, and
`ffmpeg_ok: true`.

## Validation scenarios

Ordered by story priority; each maps to spec acceptance scenarios.

1. **US1 match report**: connect Spotify (`/api/auth/spotify/login`), paste a
   test playlist URL, confirm every track gets exactly one status and totals
   add up; 100-track playlist completes < 30s (SC-001). Golden set:
   `pytest engine/tests -k golden` passes 100% (SC-003).
2. **US2 review**: open the Review Queue on a session with doubtful matches;
   resolve every item using only arrows/A/R/space; play both the local
   candidate and the Spotify original (Premium account, SDK spike R2);
   re-open the session and confirm resolutions persisted.
3. **US3 apply**: with the fixture `master.db`, apply the session; verify a
   new timestamped backup exists, readback reports every accepted match
   present, and a second apply after re-sync adds only new tracks (add-only,
   ADR 0006). Start a dummy Rekordbox process name / set the wrong version pin
   and confirm the `409` refusals name the fix. Final verification of
   Rekordbox reading the playlist happens on the owner's Mac.
4. **US4 missing**: seeded missing queue resolves ≥90% correct NL store links
   on the 20-track test set (SC-004); manual override sticks; set a track to
   `ignored`, re-sync, confirm it stays ignored; add a previously missing
   track to the fixture collection, re-sync, confirm it auto-closes (FR-023).
5. **US5 collection**: `/api/collection?query=` on a 40.000-entry index
   answers < 100ms (perf test); an mp3 and an m4a fixture play with seek; the
   ALAC fixture plays via the ffmpeg fallback; a missing file reports
   `file_missing`, no crash. Also verify `rb/reader.py`'s BPM (stored ×100
   per pyrekordbox's `anlz/tags.py`) and track-length (assumed whole
   seconds, unconfirmed against a real file) conversions against a few known
   tracks in the real fixture Collection once it lands — both were encoded
   from documentation/convention during phase 6 build, not real data
   (gate-review finding, T012).
6. **US6 enrichment**: run enrichment on the fixture collection; status shows
   coverage; interrupt the run and confirm it resumes without redoing done
   tracks (ADR 0013); manually override one track's genres and confirm a
   re-run leaves them untouched; confirm the fixture `master.db` bytes are
   identical before/after (FR-030).
7. **US7 structures**: create a structure with set-phase playlists and a
   run-of-show folder; request suggestions on a playlist with a profile
   attached and confirm filtering (genre tags, BPM) and play-count ranking;
   dismiss one suggestion and confirm it never returns; apply to the fixture
   and verify the full tree appears; edit and re-apply, confirm add-only.

## Accessibility check (every UI story)

Keyboard-only pass per story (no pointer), visible focus everywhere, contrast
via the delivered tokens, targets ≥ 24px, form errors name field + fix. Run as
part of the phase 7 review checklist; spot-check per story during phase 6.
