# Scope round 2: closed without reopening the specification

Three features from the delivered design were put back on the table on 2026-08-19,
knowing it would reopen phases 2 and 4: XML export, per-store checkout with
purchase tracking, and a watch folder that imports purchases. The owner answered
each the same day and none of them survives, so the round closes without a
specification change and phase 7 becomes reachable again.

Kept as a record rather than deleted, because "we decided not to" is the part that
gets forgotten, and the design file still shows all three.

## 1. XML export — dropped

The owner dropped it outright. It was the one that collided hardest: an export is
a second route into Rekordbox that the guard, the verified backup and the readback
all sit outside of, so SC-006's claim that every write is preceded by a verified
backup would have stopped being true of the system even while staying true of the
code. Nothing to build, nothing to reword.

## 2. Per-store checkout and purchase tracking — dropped

The owner wants iTunes and nothing else: "alleen iTunes". That settles the whole
feature, because per-store grouping, per-store totals and store-by-store handoff
only mean something with several stores. FR-020 to FR-023 stand as written, one
Store Link per Missing Track to the Apple Music / iTunes NL storefront, with the
manual override and the three states, now joined by FR-041's preview and price.

What the owner asked for instead is smaller and real: on a Mac the Store Link
should open the **Music app** rather than the browser. That needs no new store, no
purchase API and no new data, only a different URL scheme on the link the app
already stores, so it is ordinary implementation rather than scope. Recorded as
FR-042.

## 3. Watch folder — dropped

The owner will handle importing purchases their own way. This was the one that had
the app moving files inside the DJ's music library, a categorically larger
permission than anything else it does, so it is the right one to leave alone.

## Consequence

No requirement is reopened, no ADR is contradicted, and phases 2 and 4 stay as
ratified. Phase 7's review has to cover the design work that landed either way,
which it must anyway, and the gate is reachable once that is done.
