# Architecture decision records

One file per decision that shapes the architecture: a technology choice, a
rejected alternative worth remembering, a constraint that bounds later design.
Not every decision needs one — only those a future reader (human or agent)
would otherwise have to reverse-engineer from the code or re-litigate from
scratch.

## Filename format

`NNNN-short-title.md`

- `NNNN` — a 4-digit, zero-padded sequence number (`0001`, `0002`, ...
  `0016`). Numbers are never reused or renumbered, including for a superseded
  decision.
- `short-title` — kebab-case, a few words, specific enough to tell files apart
  in a directory listing (e.g. `0016-backup-rotation-keep-10-zipped.md`, not
  `0016-backups.md`).

The next number is the current highest plus one; check the directory before
adding one, don't guess from memory.

## What goes in a file

A single `#` heading that states the decision itself (not "ADR 0016" or
"Backup strategy" — the actual choice, e.g. "Backups are zip-compressed and
rotate, keeping the newest 10"), followed by prose that gives the rationale:
what was chosen, what alternatives were considered and why they were
rejected, and what constraint or prior decision it follows from. Close with
where and when it was decided (phase, and the grilling/decision reference if
there is one) so it can be traced back to the discussion that produced it.

**An ADR records the decision and its rationale — never the back-and-forth
that led to it.** No transcripts, no "first we considered X, then Y pointed
out Z, so we changed our minds" blow-by-blow. If a decision reverses an
earlier one, say so in one sentence (see 0016 superseding 0010) and point at
the reconciliation record if there is one; the deliberation itself lives in
the phase's grilling record, not here.

See any file in this directory (`0001-local-first-single-process.md` is a
short example, `0016-backup-rotation-keep-10-zipped.md` shows how a
supersession reads) for the format in practice.
