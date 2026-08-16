---
model: claude-fable-5
---

# Phase 3 — Constraints

## Purpose

Write down what bounds the solution before a solution is chosen. A constraint
discovered during architecture rewrites the architecture; a constraint discovered
during implementation rewrites the spec. This is the last cheap moment.

## Entry criteria

- Phase 2 complete, and its gate approved where the mode requires one.

## Actions

The depth of steps 2 to 4 follows `risk_class` in `specs/PROFILE.md`. At `minimal`
each of them is one recorded line with its reason; from `standard` up they are the
full artifacts described here. Step 1 is never scaled: a system without numbers is
a system nobody can review.

1. Grill the non-functionals with the human: load, latency, data volume, retention,
   availability, budget, deadline, team size, operational ownership. Every answer
   becomes a number or an explicit "unbounded, accepted".
2. NIS2: decide what is logged, what is deliberately not logged, how an incident is
   detected, who is notified within which window, and through which channel. Write
   it down now, because nobody writes it during an incident.
3. OWASP: state the security requirements ASVS-aligned, at the level the system
   warrants. Authentication, session handling, access control, input handling,
   secrets and dependency policy each get a requirement or a recorded exemption.
4. AVG/GDPR: carry the PII inventory from phase 2 forward into retention and
   deletion requirements, and name the processors.
5. Record every constraint that closes off a design option as an ADR, so phase 4 can
   cite it instead of rediscovering it.

## Deliverables

- `docs/constraints.md`, grouped by kind, each entry with a number or a verdict.
- Security requirements, ASVS-aligned.
- Logging, monitoring and incident-readiness plan.
- ADRs for the constraints that eliminate options.

## Exit criteria

- No constraint is written as an adjective: not "fast", but a number and a
  percentile, or an explicit accepted unknown.
- The logging plan says what is not logged, not only what is.
- Every personal data element has a retention period and a deletion path.
- Each security requirement is traceable to an ASVS area or marked out of scope
  with a reason.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 3`
