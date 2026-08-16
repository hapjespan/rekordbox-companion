# Agent Workflow Graph

Spec-driven development in this repository: Think First, Specify Second, Code Last.
Autonomy is front-loaded. Uncertainty that surfaces while implementing means the
specification was insufficient, so the answer is never to improvise in code: stop,
grill, update the spec, resume.

## The graph

```
0 Profile/Constitution
  -> 1 Understand
     -> 2 Specify
        -> 3 Constraints
           -> 4 Architecture
              -> 5 Tasks
                 -> 6 Implementation
                    -> 7 Review/Validate
                       -> 8 Deliver/Handover
```

One phase file per node, `00-` through `08-`, all in this directory. A phase ends
only by running `python3 .workflow/complete-phase.py <N>`. Nothing else ends a
phase, and no phase starts before its predecessor is marked complete.

## Deduplication, binding

Several installed tools cover the same ground. This table decides which one owns
which job. Anything not listed here is out of the workflow.

| Job | Owner | Not used for this |
|---|---|---|
| Elicitation, stress-testing intent | `/grill-with-docs` | `/speckit-clarify`, brainstorming skills |
| Spec artifact | `/speckit-specify`, fed by the grilling output | `/to-spec` |
| Domain language, ADRs | `/domain-modeling` | ad-hoc glossaries |
| Architecture reasoning | `/speckit-plan` plus `codebase-design` vocabulary | `/wayfinder` |
| Task breakdown | `/speckit-tasks`, gated by `/speckit-analyze` | manual task lists |
| Issues | `/speckit-taskstoissues` | `/to-tickets`, `/triage` |
| Implementation orchestration | `/speckit-implement` | Pocock `/implement` |
| Per task, inside implementation | `mattpocock-skills:tdd`, then `mattpocock-skills:code-review`, one atomic commit | any other review skill |
| Debugging | `mattpocock-skills:diagnosing-bugs` | trial and error |
| Drift, brownfield entry | `/speckit-converge` | manual reconciliation |
| Handover | `/handoff`, `/wizard`, `CONTEXT.md`, ADRs | freeform notes |

Two rules that follow from the installed set:

- **Superpowers is disabled in this project**, in `.claude/settings.json`. Its
  brainstorming, test-driven-development and systematic-debugging skills mandate a
  different order of work and would compete with this graph on every turn. Elsewhere
  on this machine superpowers stays active.
- **`code-review` is ambiguous**: both `mattpocock-skills` and the official
  `code-review` plugin ship a skill by that name. Always write the qualified form,
  `mattpocock-skills:code-review`, so the right one runs.

Disabled by this policy even though installed, never invoke: `/to-spec`,
`/to-tickets`, Pocock `/implement`, `/triage`, `/wayfinder`. `/speckit-clarify` is a
fallback only, for when grilling was explicitly skipped.

The Spec Kit commands render with a hyphen, `/speckit-specify` and so on, and
arrive as skills in `.claude/skills/` rather than as commands. That is what
version 0.16.4 installs, which is the version pinned in the image, so it does not
drift under you. `/start-project` checks the form before phase 0 starts.

## Gate modes

A gate is a stop where a human looks at the deliverables before the next phase
begins. Set in `specs/PROFILE.md`, synced into `.workflow/state.json`, read by the
Stop hook.

| Mode | Gates after phase |
|---|---|
| `autonomous` | 4, 7 |
| `standard` | 2, 4, 7 |
| `strict` | every phase |

Phases 0 to 3 need the human in the room, because they are elicitation and the work
stalls without answers only a human has. That is not the same as a gate: the state
machine gates exactly what the table above says, so in `autonomous` mode the hook
does chain 0 into 1 into 2 into 3. Run `standard` or `strict` if you want the
machine to stop there rather than relying on a phase running out of answers.

When a gate is pending, Claude stops and waits. The human approves in a terminal:

```bash
docker exec -it PROJECT-dev python3 .workflow/approve-gate.py <N>
```

Then resume the session with `continue`. When no gate is pending, the Stop hook
starts the next phase by itself, exactly once per completed phase.

## Model routing

This environment runs on a subscription with time-boxed usage limits, not
per-token billing, so routing optimises two things: limit budget (heavier models
consume the window several times faster per task) and throughput. The heavy
models go where they change outcomes; volume work runs on the standard model.

The routing is configuration, not prose. Each phase file in this directory pins
its model in frontmatter; `specs/PROFILE.md` may override one phase with a
`model_phase_<N>:` line; the three subagents under `.claude/agents/` pin the
models for the fixed roles. Scripts read that configuration and define none of
it — `.workflow/routing.py` resolves it, and the claude-config test suite holds
it to the policy. `python3 .workflow/routing.py doctor` prints the live table.

| Work | Runs on | Why |
|---|---|---|
| Phase 0, setup | phase frontmatter (standard model) | Mechanical work, preserve limit budget |
| Phases 1 to 4 | phase frontmatter (top model) | Elicitation, spec and architecture quality decide how autonomous 5 to 7 can be |
| Phase 5, decomposition | phase frontmatter (standard model) | Mechanical breakdown of an approved plan |
| Gate reviews: the phase 5 analyze gate, validation passes | `gate-review` agent | Cross-artifact consistency needs the reviewer-grade model, in every gate mode |
| Phase 6, standard tasks | phase frontmatter (standard model) | Near-top agentic coding at a fraction of the limit burn |
| Phase 6, `[complexity: high]` tasks | `task-builder-high` agent | Escalation path; deliberately a different heavy model than phase 7, so the reviewer stays clean |
| Phase 7, review and validate | phase frontmatter (top model) | Independent two-axis review and drift detection |
| Phase 8, handover | phase frontmatter (standard model) | Writing from existing artifacts |
| Changelogs, commit messages, formatting | `scribe` agent | Bulk mechanical text at near-zero limit burn |

Five rules the machine enforces rather than documents:

1. **Builder and reviewer never coincide.** Phase 6 records who built each task
   (`routing.py record-build`); phase 7 records who reviewed it
   (`routing.py record-review`), and the script refuses a reviewer equal to the
   builder. `complete-phase.py` refuses phases 6 and 7 while the ledger in
   `.workflow/model-ledger.json` is incomplete.
2. **Escalation is explicit.** Every task in `tasks.md` carries
   `complexity: standard | high` via a `[complexity: high]` marker; a missing
   marker is standard, an invalid one is an error. Only `high` routes to the
   escalation agent. The orchestrator may propose an escalation, but proposing
   means editing the flag in `tasks.md`, in a commit; `record-build` refuses an
   escalation the flag does not back.
3. **Gate reviews always run on the `gate-review` agent's model**, whatever the
   gate mode. Autonomous mode changes who approves, not who reviews.
4. **Routing lives in configuration** — frontmatter and profile — never in shell
   scripts. Scripts read it; a test in claude-config fails if a model name
   appears inside `.workflow/`.
5. **A limit pause is never a downgrade.** The Stop hook stalls a phase that
   would start on the wrong model and tells the human to switch; the
   UserPromptSubmit hook flags mid-phase drift. When a usage window runs out,
   the state machine simply does not advance: resume the same phase on the same
   model later. Model boundaries (0 to 1, 4 to 5, 6 to 7, 7 to 8) double as
   budget checkpoints — after a long standard-model batch, prefer starting the
   next heavy phase in a fresh window rather than at the tail of a spent one.

## Compliance articles

Always active. What changes with `risk_class` in `specs/PROFILE.md` is the evidence
each article demands, never whether it is answered:

| `risk_class` | What an article costs |
|---|---|
| `minimal` | One recorded line per article, including why it does not apply |
| `standard` | Full artifacts: PII inventory, incident plan, WCAG criteria per story, ten OWASP verdicts |
| `regulated` | Everything `standard` demands, plus a named owner per article and auditable evidence |

An unknown value is treated as `regulated`. The point of the scale is that
ceremony which does not earn its keep gets skipped in practice, and a process that
is skipped in practice stops being a process. A one-line "no personal data is
collected, so no inventory" is an answer; silence is not.

Each phase file states how the article applies there; these are the articles
themselves.

**AVG/GDPR.** Privacy by design and by default. Data minimisation: a field that is
not needed is not collected. Every personal data element is recorded in a PII
inventory with its lawful basis, retention period and processors. A change that adds
personal data updates that inventory in the same commit.

**NIS2.** Risk-based measures proportional to the system. Logging and monitoring
adequate to detect and reconstruct an incident, without logging the personal data
just minimised. Incident readiness: who is notified, in what window, through which
channel, written down before it is needed.

**WCAG 2.2 AA.** Every user-facing story carries accessibility acceptance criteria:
keyboard operability, focus visibility, contrast, target size, form errors that name
the field and the fix. A story without them is not ready for phase 5. Projects with
no user interface record that fact rather than silently skipping the article.

**OWASP.** Requirements are written ASVS-aligned. The Top 10 is a checklist in both
review and validation, not a slogan: authentication, access control, injection,
insecure design, misconfiguration, vulnerable dependencies, integrity, logging,
and server-side request forgery each get an explicit verdict in phase 7.
