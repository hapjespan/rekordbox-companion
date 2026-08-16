# Project profile

Filled in during phase 0, before anything else. The gate mode is synced from here
into `.workflow/state.json`, which is what the Stop hook actually reads. Change the
mode later by editing both, or by re-running the sync step in `/start-project`.

```
gate_mode: standard
deliverable_type: proof-of-value
project_type: greenfield
risk_class: minimal
deploy_target: none
tracker: github
```

## Fields

**`gate_mode`** — `autonomous`, `standard` or `strict`.
Where a human reviews before the next phase starts. `autonomous` gates after phases
4 and 7, `standard` after 2, 4 and 7, `strict` after every phase. Unknown values are
treated as `strict`, which stops more often rather than less.

**`deliverable_type`** — `proof-of-value` or `tracer-bullet`.
`proof-of-value` demonstrates that the idea is worth building and may cut depth to
get there. `tracer-bullet` runs one thin slice end to end through every layer that
production will use, and cuts breadth instead. This decides what "done" means in
phases 5 and 7, so it is not a label: write down what it excludes.

**`project_type`** — `greenfield` or `brownfield`.
`brownfield` enters phase 1 through `/speckit-converge` to establish what the code
already does before anything is specified about what it should do.

**`risk_class`** — `minimal`, `standard` or `regulated`.
How deep the four compliance articles are worked in phases 2, 3 and 7. The articles
themselves are never dropped; what changes is the evidence they demand.

- `minimal`: nothing user-facing beyond yourself, no personal data, no production
  exposure. Each article is answered in one recorded line, including why it does
  not apply. A weekend proof-of-value lives here.
- `standard`: real users or real data, self-hosted. Full PII inventory, full
  logging and incident plan, WCAG criteria per user-facing story, ten OWASP
  verdicts in phase 7.
- `regulated`: personal data at scale, a client, or a legal obligation. Everything
  `standard` demands, plus a named owner per article and evidence a third party
  could audit.

An unknown value is treated as `regulated`, the same way an unknown `gate_mode` is
treated as `strict`. Raising the class mid-project is normal; lowering it is a
decision that gets written down with its reason.

**`deploy_target`** — `coolify`, `none` or a named platform.
Where phase 8 delivers to. `coolify` is the platform running on the development
host, reachable on the host itself; `none` means the project is explicitly not
deployed, which phase 8 records rather than silently skips. A target other than
these two means writing the deploy step for it in phase 8 before you get there.

**`tracker`** — `github`.
Issues are created with `/speckit-taskstoissues`. Another tracker means a different
issue step, and `/to-tickets` stops being disabled.

**`model_phase_<N>`** — optional, absent by default.
Model routing is configuration: each phase file in `docs/process/` pins its model
in frontmatter, per the routing policy in `docs/process/workflow.md`. A project
that must deviate adds a line to the block above, for example
`model_phase_6: claude-opus-4-8`, and records the reason in prose here. An
override changes one phase's model and nothing else. The hard rules survive any
override, because they are enforced elsewhere: gate reviews run on the
`gate-review` agent's model in every mode, escalation happens only through the
`[complexity: high]` flag in `tasks.md`, and `routing.py` refuses a phase 7
reviewer equal to a task's recorded builder. `python3 .workflow/routing.py doctor`
shows what actually resolves.

## Scope note

One paragraph, written during phase 0: what this project is for, and the sharpest
thing it is explicitly not for. Phase 7 checks the result against this paragraph.
