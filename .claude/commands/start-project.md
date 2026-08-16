---
description: Initialise the Agent Workflow Graph in this project and enter phase 0
---

Bring this project from a scaffolded repository to a running spec-driven workflow.
Run this inside the project container, not on the host. Execute the steps in order
and stop at the first failure rather than working around it.

## 1. Preflight

Report a version per component and abort on anything missing:

```bash
python3 --version
git --version
specify --help | head -1
gh auth status
```

`specify` and `uv` live in the image. If `specify` is missing, the container was
built before the toolchain was added: rebuild it from the host with
`docker compose build --no-cache` and start again.

Confirm the process files that kickoff placed here actually exist:
`docs/process/workflow.md`, `docs/process/00-profile-and-constitution.md` through
`08-deliver-handover.md`, `specs/PROFILE.md`, `.workflow/state.json`,
`.workflow/complete-phase.py`, `.workflow/approve-gate.py`, `.workflow/routing.py`,
`.workflow/hooks/next-phase.py`, `.workflow/hooks/check-model.py`, and the three
routing agents `.claude/agents/gate-review.md`, `.claude/agents/task-builder-high.md`
and `.claude/agents/scribe.md`. If any are missing, say so and stop: they belong
to the kickoff assets and should not be improvised here.

Then confirm the model routing resolves, which proves the frontmatter, the profile
and the agent files agree:

```bash
python3 .workflow/routing.py doctor
```

It prints the model per phase and per agent and exits non-zero on any gap. This
table is the routing policy from `docs/process/workflow.md` as configuration;
scripts read it and never define it.

## 2. Install the Spec Kit project files

```bash
specify init --here --force --integration claude
```

`--force` is required because this directory is never empty. Spec Kit writes into
`.claude/skills/` and `.specify/`, and this step runs before step 3 because older
versions also rewrote `.claude/settings.json`.

Then confirm what the commands are actually called, instead of assuming:

```bash
ls .claude/skills/ | grep -i speckit
```

Pinned at 0.16.4, which is what the image installs, they render with a hyphen and
arrive as skills rather than commands: `/speckit-specify`, `/speckit-plan` and so
on. That is the form the phase files use. If you see dots instead, the image was
built from an older pin: say so and stop rather than editing nine documents.

The workflow needs all ten to exist: constitution, specify, plan, tasks, analyze,
taskstoissues, implement, converge, checklist, clarify. Report any that are absent
and stop.

## 3. Verify the Stop hook survived

Spec Kit 0.16.4 leaves an existing `.claude/settings.json` alone, which was checked
by running it; earlier versions replaced it. Rather than trusting either, put back
whatever might have been dropped, without touching what was added:

```bash
python3 .workflow/merge-claude-settings.py .claude/settings.json \
    --from .workflow/required-settings.json
```

It restores four things: the Stop hook running
`python3 "$CLAUDE_PROJECT_DIR/.workflow/hooks/next-phase.py"`, the UserPromptSubmit
hook running `python3 "$CLAUDE_PROJECT_DIR/.workflow/hooks/check-model.py"` (which
flags a session doing phase work on the wrong model), the `enabledPlugins` entry
disabling superpowers, and the `permissions.deny` list that blocks
`approve-gate.py`. It only adds, so run it as often as you like; a second run
prints that the file already has everything it needs. Never replace the file
wholesale by hand.

The deny list is what keeps a gate a gate. Verify it actually bites, from this
session, and expect the call to be refused:

```bash
python3 .workflow/approve-gate.py 0
```

Two things must hold: the harness refuses the Bash call, and if you reach the
script another way it refuses itself because `CLAUDECODE` is set. A human approves
from a plain terminal in this container, where neither applies.

Then make the scripts executable and dry-run the hook:

```bash
chmod +x .workflow/*.py .workflow/hooks/*.py
echo '{"stop_hook_active":false}' | python3 .workflow/hooks/next-phase.py
```

With `last_completed_phase` at `-1` the hook must print nothing and exit 0. Output
at this point means the state file is wrong; fix it before continuing.

## 4. Fill the profile

If `specs/kickoff.md` exists, read it first: it is the base set the user handed at
kickoff and confirmed there. Propose the six answers and the scope note from it in
one message and have the user confirm the set; ask only what the file leaves open
or contradicts.

Otherwise work through `specs/PROFILE.md` with the user. Ask rather than assume,
and keep it to these six decisions:

- `gate_mode`: `autonomous` (gates after phases 4 and 7), `standard` (after 2, 4
  and 7) or `strict` (after every phase).
- `deliverable_type`: `proof-of-value` or `tracer-bullet`.
- `project_type`: `greenfield` or `brownfield`. Brownfield enters the graph with
  `/speckit-converge` in phase 1.
- `risk_class`: `minimal`, `standard` or `regulated`. Decides how much evidence the
  four compliance articles demand in phases 2, 3 and 7, never whether they apply.
  Ask what the project touches: real users, personal data, public exposure.
- `deploy_target`: `coolify`, `none` or a named platform. Phase 8 delivers to it.
- `tracker`: `github`.

Sync the chosen gate mode into the state machine, because the hook reads it from
there and not from the profile:

```bash
python3 - <<'PY'
import json, pathlib, re
mode = re.search(r"^gate_mode:\s*(\S+)", pathlib.Path("specs/PROFILE.md").read_text(), re.M).group(1)
state = json.loads(pathlib.Path(".workflow/state.json").read_text())
state["gate_mode"] = mode
pathlib.Path(".workflow/state.json").write_text(json.dumps(state, indent=2) + "\n")
print("gate_mode =", mode)
PY
```

## 5. Commit and hand over

```bash
git add -A && git commit -m "chore: initialise agent workflow graph"
```

Report in Dutch: component versions, the Spec Kit command names as they actually
render, gate mode, the model routing table from `routing.py doctor`, and
confirmation that the hook dry-run was silent.

Then start phase 0 by reading `docs/process/00-profile-and-constitution.md` and
executing it. Phase 0 is routed to the model in that file's frontmatter; if this
session runs a different model, ask the user to switch with `/model` before
starting. The phase ends, as every phase does, with
`python3 .workflow/complete-phase.py 0` and nothing else.
