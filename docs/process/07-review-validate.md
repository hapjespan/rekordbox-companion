---
model: claude-opus-5
---

# Phase 7 — Review and validate

## Purpose

Verify the result against the specification and the compliance articles, not against
what everyone remembers intending. Review looks at the change; validation looks at
whether the thing that was built is the thing that was specified.

## Entry criteria

- Phase 6 complete, every task merged into `release`, test suite green on `release`.
  This phase reviews what the release pull request in phase 8 will contain, so it
  runs against `release` and not against a feature branch.
- Spec, constraints, PII inventory and the scope note from `PROFILE.md` available.
- The session runs the model this phase is routed to; the Stop hook stalls the
  phase until it does. The routing keeps this reviewer independent by design:
  phase 6 escalates to a different heavy model precisely so the reviewer here never
  reviews its own implementation work. This holds in every gate mode; autonomous
  mode changes who approves the gate afterwards, not who reviews.

## Actions

Steps 2 to 5 follow `risk_class` in `specs/PROFILE.md`: at `minimal` each article
gets one recorded verdict line, from `standard` up they get the full treatment
described here, and at `regulated` each also carries a named owner. Step 1 and
step 6 are never scaled.

1. Two-axis review over the whole change set: correctness, then design. Correctness
   asks whether it does what the spec says; design asks whether the next change will
   be cheap. Per task, record the review:
   `python3 .workflow/routing.py record-review <TASK> <model>`, with the model that
   reviewed it. The script refuses a reviewer equal to the recorded builder, which
   is the rule this routing exists for: the model that implemented a task never
   reviews that task.
2. OWASP Top 10: give each of the ten an explicit verdict for this system, with
   evidence. "Not applicable" is a valid verdict; silence is not.
3. WCAG 2.2 AA: check the user-facing result against the criteria written in phase
   2. A deviation is recorded with an owner and a date, never left implicit.
4. AVG/GDPR: reconcile the PII inventory against what the code actually stores and
   logs. A field in the database that is not in the inventory is a finding.
5. NIS2: verify the logging and monitoring plan from phase 3 is implemented and that
   an incident could actually be reconstructed from what is logged.
6. Validate the result against the scope note in `specs/PROFILE.md`, including the
   part that says what the project is not for.

## Deliverables

- Review report covering both axes.
- Ten OWASP verdicts with evidence.
- WCAG conformance statement, including any recorded deviations.
- Reconciled PII inventory.

## Exit criteria

- Every OWASP Top 10 item has an explicit verdict.
- The user-facing result meets WCAG 2.2 AA, or each deviation has an owner and a
  date.
- The PII inventory matches what the code stores and logs, in both directions.
- The result matches the scope note, and any drift from it is written down rather
  than absorbed.
- `python3 .workflow/routing.py check 7` passes: every task has a recorded reviewer
  that is not its builder. `complete-phase.py` refuses the phase otherwise.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 7`

A human gate follows this phase in every mode. Claude stops; the human approves with
`docker exec -it PROJECT-dev python3 .workflow/approve-gate.py 7`, from a terminal.
