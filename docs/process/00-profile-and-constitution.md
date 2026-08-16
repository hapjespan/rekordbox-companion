---
model: claude-sonnet-5
---

# Phase 0 — Profile and constitution

## Purpose

Decide how this project will be run and what it will never trade away, before any
thinking about the problem starts. The profile fixes the operating mode, the
constitution fixes the non-negotiables. Both are cheap now and expensive later:
every phase after this one reads them.

## Entry criteria

- `/start-project` has completed and its dry-run of the Stop hook was silent.
- `specs/PROFILE.md` and `.specify/` exist.

## Actions

1. Fill every field in `specs/PROFILE.md` with the user. Ask, never assume, and
   write the scope note paragraph including what the project is explicitly not for.
   If `specs/kickoff.md` exists it is the base the user handed and confirmed at
   kickoff: propose the answers and the scope note from it and have the user
   confirm the set, instead of asking each question blind.
2. Sync the chosen mode into the state machine, which is what the hook reads:
   `python3 - <<'PY'` … as described in `/start-project` step 4, or edit
   `.workflow/state.json` by hand and keep the two in step.
   Model routing needs no decision here: the defaults ship in the phase files'
   frontmatter, per the routing policy in `docs/process/workflow.md`. A project
   that must deviate records a `model_phase_<N>:` override in `specs/PROFILE.md`
   with its reason, which is rare and never touches the hard rules.
3. Run `/speckit-constitution` and give it:
   - the five pillars of this project, derived from the scope note;
   - the engineering baseline: test-driven development per task, two-axis review
     (correctness and design), one atomic commit per task;
   - the four compliance articles from `docs/process/workflow.md`, quoted as
     articles rather than summarised.

## Deliverables

- `specs/PROFILE.md`, fully filled, including the scope note.
- `.specify/memory/constitution.md`.
- `.workflow/state.json` with `gate_mode` equal to the profile.

## Exit criteria

- No field in `specs/PROFILE.md` is still at its template default by accident: each
  one was discussed and confirmed.
- The scope note names at least one thing the project will not do.
- The constitution names all four compliance articles and the engineering baseline.
- `gate_mode` in `.workflow/state.json` matches `specs/PROFILE.md`.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 0`
