---
model: claude-sonnet-5
---

# Phase 5 — Tasks

## Purpose

Decompose the plan into tasks that are independently verifiable and small enough
that one of them is one commit. The quality of this decomposition decides how much
of phase 6 can run without a human.

## Entry criteria

- Phase 4 complete and its gate approved.
- The plan and the seam map exist.

## Actions

1. Run `/speckit-tasks`.
2. Flag complexity on every task line in `tasks.md`. The default is standard and
   needs no marker; append `[complexity: high]` only where the escalation criteria
   hold: a cross-cutting change, a data migration, tricky concurrency, or a security
   boundary. A `high` flag carries its reason in the task text. This flag is the
   single source of truth for model routing in phase 6: a task without it builds on
   the standard model, and nothing escalates a task except editing this file. The
   orchestrator may propose an escalation later, but proposing means editing the
   flag here, in a commit, so the diff is the audit trail.
3. Run the `/speckit-analyze` gate through the `gate-review` subagent: give it the
   spec, plan, tasks and constitution, and have it judge cross-artifact consistency
   and the complexity flags. Gate reviews run on the model pinned in
   `.claude/agents/gate-review.md` in every gate mode; autonomous mode changes who
   approves, not who reviews. Treat its blocking findings as blocking: fix the
   decomposition and re-run rather than proceeding with known gaps.
4. Check every task against the deliverable type in `specs/PROFILE.md`. A
   `tracer-bullet` cuts breadth and keeps every layer; a `proof-of-value` cuts depth
   and may stub a layer. Whichever it is, the cut is written into the task.
5. Carry the acceptance criteria from phase 2 down into the tasks, WCAG criteria
   included, so that no task has to look them up later.
6. Run `/speckit-taskstoissues` to create the GitHub issues.

## Deliverables

- The Spec Kit tasks artifact, every task carrying a deliberate complexity flag
  (standard by omission, `[complexity: high]` with a reason).
- The gate review report from the `gate-review` subagent, with every finding
  resolved or explicitly waived.
- One GitHub issue per task.

## Exit criteria

- The gate review reports no unresolved blocking findings.
- Every task carries its own acceptance criteria and touches one concern.
- Every user-facing task carries its WCAG criteria.
- Every task has an issue, and every issue traces back to a story in the spec.
- `python3 .workflow/routing.py check 5` passes: the task list parses and every
  complexity flag is valid. `complete-phase.py` refuses the phase otherwise.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 5`
