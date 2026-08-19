# Backlog carried out of the phase 7 review

Findings from the phase 7 two-axis review that were recorded rather than fixed in
that phase, each with the reason it was not fixed. The thirteen blocking findings
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

## B2 — Backups must include the SQLite sidecars — ANSWERED, and it is a defect

No longer an open question. `master.db` demonstrably uses a write-ahead log: a
`master.db-wal` appeared beside the owner's own fixture copy carrying committed
data, and SQLite replayed it onto a freshly copied base file, resurrecting a
playlist an earlier apply had written. That was observed in the dev container, so
it did not need the Mac after all.

Consequence for the product: `rb/backup.py` zips `master.db` and
`masterPlaylists6.xml` and nothing else, so a backup taken while a `-wal` holds
committed frames verifies readable while missing the newest transactions. That
undercuts SC-006's "verified Backup" for precisely the case backups exist for.
The fix is to checkpoint before copying, or to include both sidecars in the zip
and restore them together; checkpointing is the safer of the two because a base
file plus a foreign sidecar is what caused the surprise in the first place.

Raised from a question to a defect on 2026-08-19. Not fixed in the same breath
because it changes the write path's most safety-critical helper, which deserves
its own change with its own tests rather than riding along with UI work.

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

## B6 — Drive the keyboard through the densest interactive states

Narrowed twice. The shell revision made
`web/tests/e2e/accessibility.spec.ts` loop all five workspace views, but its
mocked session had `review: 0` and its `/api/structures` answered `[]`, so the
two densest surfaces still rendered empty. A third test now scans them
populated: a review card with two resolved candidates and one the collection
does not know, and a structure with two phase columns holding tracks with and
without a BPM and a musical key, plus the BPM chart's text alternative folded
open. That closes the coverage half.

What remains is depth rather than coverage. axe scans a rendered state; it does
not tab through a roving-tabindex table, resolve a review item by keyboard, or
re-parent a node in the tree, and those are the interactions where a focus trap
or a lost focus position would actually show up. Owner: Martien, 2026-09-01.

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

## B9 — Give the page a real heading structure — CLOSED

Closed by the shell revision, which was the cheap moment to do it: each view now
has a real heading outline instead of styled paragraphs, and the panel titles that
merely repeated their view's heading were removed rather than nested.

## B10 — Reconsider the single-page layout once every story has a screen — CLOSED

Overtaken by the owner's shell design, which answers exactly this: five workspace
views behind a sidebar, one screen at a time, instead of one scrolling column.

## B11 — Consider a router, now that there are five views

The shell holds the current view in component state, so the view is not in the
URL: it cannot be linked, bookmarked, or restored by a reload, and the browser's
back button does nothing. That is defensible for a single-operator local tool and
the delivered prototype does the same, but it is the kind of thing that gets
noticed on the tenth reload rather than the first.

## B12 — Decide whether the match report needs its own buy controls

Note added 2026-08-19: the match report's missing rows now say "Koop via de
wachtrij" and their pill navigates there, because `GET /api/missing` exposes no
`sync_track_id`, so there is no reliable key to join a store link onto a sync row.
Building the inline cell therefore needs that id on the missing row first. Whether
it is worth it is still the owner's call.

### Original entry

The delivered design puts a store cell on every row of Match-overzicht's
"Ontbreekt in Rekordbox" group: store, price and a call to action per track. What
shipped instead is the design's own hero action, "Ontbrekende naar wachtrij",
which carries the DJ one click to the buy queue where FR-041's preview, the price
and the store link all live. That satisfies seeing the result and acting on it,
and it keeps one place that owns playback and purchase state.

Building the inline cell as well would mean exposing each missing row's store
fields on the sync-session detail and running a second preview player, so it is a
question about duplication rather than a missing capability. Belongs with the
owner after a few real playlists have gone through.
