---
model: claude-fable-5
---

# Phase 2 — Specify

## Purpose

Turn the understanding from phase 1 into a specification complete enough to build
from without asking a follow-up question. This is the artifact that later phases are
measured against, so ambiguity left here is paid for in phase 6.

## Entry criteria

- Phase 1 complete.
- The grilling output and glossary exist and are the source for this phase.

## Actions

1. Run `/speckit-specify`, fed by the phase 1 grilling output. Do not re-elicit
   here: if a question comes up that grilling did not answer, go back to phase 1
   rather than inventing an answer.
2. Write acceptance criteria for every story. WCAG 2.2 AA criteria are mandatory on
   every user-facing story: keyboard operability, visible focus, contrast, target
   size, and form errors that name both the field and the fix.
3. Start the PII inventory: every personal data element the spec implies, with its
   lawful basis, retention period and any processor that touches it. A field nobody
   can justify is removed from the spec here, not audited away later. At
   `risk_class: minimal` this is one recorded line stating that the spec implies no
   personal data, and it stops being one line the moment the spec implies any.
4. `/speckit-clarify` is a fallback only, for the case where grilling was explicitly
   skipped. Using it after a proper phase 1 means the grilling was not finished.

## Deliverables

- `specs/<feature>/spec.md`.
- The PII inventory, in `specs/` next to the spec.
- Updated glossary if the spec introduced a term.

## Exit criteria

- Every story has acceptance criteria that a test could be written from directly.
- Every user-facing story carries WCAG 2.2 AA criteria. A project with no user
  interface records that fact once instead of skipping the article.
- No story contains "etc", "and so on", or a list that trails off.
- The PII inventory covers every personal data element in the spec, each with a
  lawful basis and a retention period, or states in one line that there are none.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 2`

In `standard` and `strict` mode a human gate follows this phase. Claude stops; the
human approves from a terminal with
`docker exec -it PROJECT-dev python3 .workflow/approve-gate.py 2`.
