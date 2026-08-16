---
model: claude-sonnet-5
---

# Phase 8 — Deliver and hand over

## Purpose

Make the result operable and understandable by someone who was not in the room. The
test of this phase is not whether the documents exist, but whether a new engineer
could take over from them alone.

## Entry criteria

- Phase 7 complete and its gate approved.
- Findings from phase 7 either fixed or recorded with an owner and a date.

## Actions

1. Release: open a pull request from `release` to `main` and merge it. Phase 7
   validated `release`, so this is the moment that work becomes the released state.
   Nothing is pushed to `main` directly, and the hook refuses it if tried.

2. Deploy to the `deploy_target` from `specs/PROFILE.md`, or record why not.
   - `coolify`: create the application in Coolify on the development host, point it
     at the GitHub repository and at `main`, set the environment variables from
     `.env.example` (never the values from `.env`), attach it to the database it
     needs, and deploy. Write down the resulting URL, the Coolify project name and
     how a rollback is triggered.
   - `none`: state in one line that this project is deliberately not deployed, and
     what would have to change for that to stop being true. This is a valid answer,
     but only as a written one.
   - Anything else: write the deploy step for that platform here before running it,
     so the next project inherits it.
3. Run `/handoff` to produce the handover document. Bulk mechanical text in this
   phase — the changelog, release notes, formatting passes over the documents —
   drafts through the `scribe` subagent, so it costs the cheapest model instead of
   this session's. The judgment calls in the handover stay here.
4. Run `/wizard` for the operational walkthrough: how it is run, deployed, observed
   and rolled back. A `none` target still needs the run and observe halves.
5. Finalise `docs/CONTEXT.md` so every ADR is reachable from it, and every term in
   the glossary still matches the code.
6. Write the runbook: how an incident is detected, who is notified and in what
   window, per the NIS2 plan from phase 3. A project at `risk_class: minimal` with
   `deploy_target: none` writes the one line that says so instead.
7. Run `/retro` to distil this project's lessons into the central knowledge base.
   One lesson per file with frontmatter and `related` links, as that repository
   requires. This is the retro for the whole project: the shared retro Stop hook
   deliberately stays silent while the graph is unfinished, and starts firing again
   once phase 8 is complete.

## Deliverables

- `release` merged into `main` through a pull request, so `main` is the released state.
- A deployed application at a recorded URL, or the recorded reason there is none.
- Handover document.
- `docs/CONTEXT.md`, final, linking every ADR.
- Runbook, including incident notification.
- Lessons written to the knowledge base.

## Exit criteria

- The `deploy_target` from the profile is either live and reachable, or explicitly
  recorded as not deployed with the reason.
- A new engineer can start the project from the documents alone, without access to
  this conversation.
- Every ADR is reachable from `CONTEXT.md`, and no ADR contradicts the code.
- The runbook names people or roles, not "someone".
- The knowledge base contains this project's lessons.

## Transition

On completion, run: `python3 .workflow/complete-phase.py 8`

That is the last phase; the Stop hook goes quiet after it.
