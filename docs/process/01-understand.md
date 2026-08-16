---
model: claude-fable-5
---

# Phase 1 — Understand

## Purpose

Establish what the problem is, whose problem it is, and what already exists. No
solution is chosen here. The output of this phase is the input that makes phase 2
writable without a single follow-up question.

## Entry criteria

- Phase 0 complete.
- The constitution exists and has been read.

## Actions

1. Brownfield only: run `/speckit-converge` first, to establish what the code
   already does before anything is claimed about what it should do. Greenfield
   projects skip this step and say so.
2. Run `/grill-with-docs` on the problem statement. This is the elicitation step
   for the whole workflow, so it happens with the human present. Push until the
   answers stop changing, not until they sound reasonable.
3. Run `/domain-modeling` to pin the ubiquitous language, write `docs/CONTEXT.md`
   and record decisions that are already fixed as ADRs.
4. Name the three biggest unknowns explicitly. An unknown that survives this phase
   becomes a constraint or a risk in phase 3, never a surprise in phase 6.

## Deliverables

- `docs/CONTEXT.md` with the domain narrative and the glossary.
- ADRs for decisions that were already made before this project started.
- The grilling output, kept, because phase 2 is fed from it.
- Brownfield: the `/speckit-converge` report.

## Exit criteria

- The problem fits in one paragraph that names no technology.
- Every domain term used later appears in the glossary exactly once, with one
  meaning.
- The three biggest unknowns are written down, each with who can answer it.
- Nothing in this phase's output states how the solution works.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 1`
