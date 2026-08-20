---
model: claude-opus-5
---

# Phase 4 — Architecture

## Purpose

Choose a structure and justify it against the constraints from phase 3. The output
is a plan that a competent engineer could implement without guessing, and that a
reviewer can argue with because the rejected alternatives are on the record.

## Entry criteria

- Phase 3 complete.
- `docs/constraints.md` and the ADRs from phases 1 and 3 exist.

## Actions

1. Run `/speckit-plan`.
2. Reason about module boundaries in the vocabulary of `codebase-design`: depth,
   interface, seam, adapter, locality. Name the seams where the system will be
   tested and where it will later be changed.
3. Grill the resulting plan with `/grill-me`. A plan that survives its own author
   has not been tested.
4. Record at least one seriously considered alternative that was rejected, with the
   constraint that killed it. If nothing was rejected, the design space was not
   explored.
5. Map every constraint from phase 3 onto either a design decision or an explicitly
   accepted risk with an owner.

## Deliverables

- The Spec Kit plan artifact.
- ADRs for the architectural decisions, including the rejected alternatives.
- A module and seam map, in `docs/`, readable without the code open.

## Exit criteria

- Every constraint from phase 3 maps to a decision or an accepted risk; none is
  silently dropped.
- At least one rejected alternative is recorded with its reason.
- The seams named in the plan are the seams the tests in phase 6 will use.
- The plan states how the deliverable type from `PROFILE.md` shapes it: what depth
  or breadth is deliberately cut.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 4`

A human gate follows this phase in every mode. Claude stops; the human approves with
`docker exec -it PROJECT-dev python3 .workflow/approve-gate.py 4`, from a terminal.
