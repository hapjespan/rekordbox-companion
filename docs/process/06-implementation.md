---
model: claude-sonnet-5
---

# Phase 6 — Implementation

## Purpose

Build it, one task at a time, with the specification as the only source of truth.
This phase writes code; it does not decide anything. A decision that has to be made
here is proof that an earlier phase was incomplete.

## Entry criteria

- Phase 5 complete.
- Issues exist and `/speckit-analyze` came back clean.

## Actions

1. Run `/speckit-implement` to orchestrate the task list.
2. Per task, route first: `python3 .workflow/routing.py task <TASK>` names the model
   that builds it, from the complexity flag in `tasks.md` and nothing else.
   - Standard tasks are built in this session, which runs on this phase's model.
   - `[complexity: high]` tasks are dispatched to the `task-builder-high` subagent,
     whose model is pinned in `.claude/agents/task-builder-high.md`. Hand it the one
     task, its acceptance criteria and the relevant spec and plan excerpts.
   - If a task turns out to need escalation mid-phase, do not silently build it on
     the heavier model: edit its flag in `tasks.md` with the reason, commit that,
     and then dispatch. `routing.py record-build` refuses an escalation the flag
     does not back.
3. Per task, in this order, without exception:
   - `mattpocock-skills:tdd` first: a failing test that expresses the acceptance
     criteria, before any implementation code exists.
   - Implement until that test passes and no other test broke.
   - `mattpocock-skills:code-review` on the change, on both axes: correctness and
     design. Use the qualified name, because the official `code-review` plugin ships
     a skill with the same short name.
   - One atomic commit, referencing the issue, conventional commit format, on a
     feature branch cut from `release`. Draft the commit message through the
     `scribe` subagent, which exists so bulk mechanical text never burns the heavier
     models' limit. It lands on `release` when its review passes, and nothing here
     goes near `main`: that step belongs to phase 8.
   - Record the builder: `python3 .workflow/routing.py record-build <TASK> <model>`,
     with the model that actually built it. Phase 7 reads this ledger to guarantee
     that no task is reviewed by the model that built it, and `complete-phase.py`
     refuses to end this phase while any task lacks its record.
4. Debugging goes through `mattpocock-skills:diagnosing-bugs`. Changing lines until
   the symptom disappears is not debugging and leaves the cause in place.
5. When uncertainty appears, stop. Do not resolve it in code. Go back to phase 2 or
   3, grill it out, update the artifact, and resume. Front-loaded autonomy is the
   whole point: implementation-time uncertainty means the spec was insufficient.

## Deliverables

- Code and tests, one atomic commit per task.
- Closed issues, each closed by the commit that implemented it.
- Updated PII inventory if implementation touched personal data.

## Exit criteria

- Every task is committed atomically and its issue is closed.
- The test suite is green, and every task added at least one test that would fail
  without its change.
- No task was closed with a review skipped.
- Nothing was decided in this phase that is not reflected back in the spec or an
  ADR.
- `python3 .workflow/routing.py check 6` passes: every task has a recorded builder
  consistent with its complexity flag. `complete-phase.py` refuses the phase
  otherwise.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 6`
