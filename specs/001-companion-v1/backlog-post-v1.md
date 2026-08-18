# Backlog carried out of the phase 7 review

Findings from the phase 7 two-axis review that were recorded rather than fixed in
that phase, each with the reason it was not fixed. The eleven blocking findings
were fixed inside phase 7 and are listed in `review-phase-7.md`; nothing here is
a defect the owner can currently reach and be harmed by.

This is deliberately not in `tasks.md`. The phase machine judges phases 6 and 7
against every task line in `specs/**/tasks.md` and refuses to complete either
while one lacks a recorded builder, so unbuilt future work in that file would
make the phase uncompletable. Phase 8 handover picks this file up instead.

## B1 — Make the guarded-write invariant structural, not remembered

`api/sync.py` and `api/structures.py` each duplicate the
guard → backup → write → audit orchestration by hand, and nothing mechanical
stops a third endpoint from calling `writer.apply_*` directly. Extract one shared
apply-orchestrator and add a conformance test that fails on any `pyrekordbox`
import outside `engine/src/companion/rb/` and any `writer.apply_*` caller outside
the orchestrator. Deferred out of phase 7 because it refactors code that is
correct: the invariant holds today, it is just convention rather than structure.
That conformance test also closes B3 mechanically.

## B2 — Decide whether backups must include the SQLite sidecars

`rb/backup.py` zips `master.db` and `masterPlaylists6.xml` but not the
`-wal`/`-shm` sidecars. If Rekordbox 7.2.17 runs `master.db` in WAL mode and
exits uncleanly, a backup verifies readable while missing the newest
transactions. Verify WAL usage on the Mac against the real install; if WAL is in
use, include or checkpoint the sidecars. Cannot be answered in the dev container.

## B3 — Reconcile ADR 0017 with the test-side pyrekordbox imports

`engine/tests/rb/test_writer_integration.py` and
`engine/tests/bookings/test_structure_apply.py` import `pyrekordbox` directly to
verify the writer with something other than the writer. That is sound test
design, but it sits outside ADR 0017's stated exception, so the rule's wording
and the practice disagree. Widen the ADR, or route the verification through a
read-only wrapper.

## B4 — Render enrichment progress instead of only probing for completion

`EnrichmentPanel.tsx` receives the per-chunk `enrichment_progress` SSE events but
uses them only as a completion probe, so during a multi-hour run the status line
and the coverage number stay frozen. That is the opposite of why ADR 0014 chose
SSE.

## B5 — Reconcile the logging plan with the implementation

`docs/constraints.md` says logs are local files rotated by size, while
`configure_logging()` installs a `StreamHandler`, so logs go to the terminal that
runs the app and are not rotated files. Either implement rotating file logging or
amend the plan. Recorded as the one deviation under the A09 verdict in
`review-phase-7.md`.

## B6 — Extend the accessibility sweep to the densest interactive states

`web/tests/e2e/accessibility.spec.ts` covers the default page state and the
match-report and apply flow, but not the review queue or the booking-tree editing
states. Those were unreachable while the US2 review UI was unwired (phase 7
blocking finding 3); now that it is mounted, the sweep should include them.
Owner: Martien, 2026-09-01.

## B7 — Run the manual half of the accessibility pass

A keyboard-only walkthrough of every user-facing flow and physical measurement of
the 24x24 minimum target size. Specified in phase 2, never executed, and not
delegable to CI: it needs the owner at the keyboard. Owner: Martien, 2026-09-01.

## B8 — Consider applying migrations at app startup as well

`make setup` now runs `alembic upgrade head`, which closes the fresh-install
failure phase 7 found. `create_app()` still applies no migrations, so starting
uvicorn directly without ever running `make setup` reproduces the original "no
such table". Left as a deliberate choice for now, because a migration side effect
at import time is worse design than a documented setup step; revisit if the Mac
install turns out to bypass `make setup`.
