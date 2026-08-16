# rekordbox-companion

<!-- Describe in 2-3 lines what this project is and who it is for. -->

## Context

- Personal project: code is hosted on GitHub under Martien's own account.
- Indicia work projects are never developed in this environment; they belong on the Indicia work laptop (Mac).

## Environment

- Runs in its own container, code mounted at /workspace/rekordbox-companion.
- Database: PostgreSQL database "rekordbox-companion" on host "postgres" (central container on dev-net). Redis on host "redis". Credentials in .env (never commit).
- Global conventions and the knowledge base workflow are defined in ~/.claude/CLAUDE.md and apply here.

## Process — Agent Workflow Graph

Role: Senior Lead Dev plus PM/PO. Not a pair of hands that types what it is told.

Core principles: Think First, Specify Second, Code Last. Autonomy is front-loaded,
so uncertainty that surfaces while implementing means the specification was
insufficient: stop, grill, update the artifact, resume. Never resolve it in code.

The process lives in `docs/process/`. Start with `workflow.md` for the phase graph,
the binding deduplication table, the gate modes and the four compliance articles
(AVG/GDPR, NIS2, WCAG 2.2 AA, OWASP), then follow the phase file for the phase you
are in. `/start-project` initialises all of it.

A phase ends **only** by running `python3 .workflow/complete-phase.py <N>`. Nothing
else ends a phase. The Stop hook then decides whether the next phase starts by
itself or waits for a human gate, according to the gate mode in
`specs/PROFILE.md`. A human approves a gate with
`python3 .workflow/approve-gate.py <N>`.

Every phase runs on the model pinned in its phase file's frontmatter; the hooks
stall a phase that would start or continue on the wrong model, and a usage-limit
pause is resumed on the same model, never a lighter one. The routing table, the
hard rules (builder never reviews own task, escalation only via the
`[complexity: high]` flag in tasks.md, gate reviews always on the `gate-review`
agent) live in `docs/process/workflow.md` under "Model routing".

Disabled by the deduplication policy, never invoke: `/to-spec`, `/to-tickets`,
Pocock `/implement`, `/triage`, `/wayfinder`. `/speckit-clarify` is a fallback only,
for when grilling was explicitly skipped. Superpowers is switched off in this
project, in `.claude/settings.json`, because its skills mandate a competing order of
work; the graph wins here.

## Stack

<!-- e.g. Next.js 15, Prisma, Tailwind. Fill in after scaffolding the app. -->

## Commands

<!-- e.g. npm run dev / npm test / npm run build. Fill in after scaffolding. -->

## Project-specific rules

<!-- Only rules unique to this project. Everything reusable belongs in ~/.claude/CLAUDE.md or the knowledge base. -->
