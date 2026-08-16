# Bootstrap Prompt — Agent Workflow Graph

Paste everything below the line into Claude Code, once per repository. It verifies and installs the toolchain, materializes the process as `.md` files, and wires a Stop hook that chains phases autonomously according to the project's gate mode.

---

You are bootstrapping the **Agent Workflow Graph** process (spec-driven development: Think First, Specify Second, Code Last) in this repository. Execute all steps in order. Never continue past a failed step — stop and report. Finish with the self-check in Step 5.

## Step 1 — Preflight: verify, install, update the toolchain

Check each component. Install if missing, update if outdated. Report version per component.

| # | Component | Check | Install | Update |
|---|-----------|-------|---------|--------|
| 1 | git | `git --version` | (manual — abort if missing) | — |
| 2 | jq | `command -v jq` | `sudo apt-get install -y jq` / `brew install jq` | — |
| 3 | GitHub CLI (`gh`) | `gh auth status` | https://cli.github.com + `gh auth login` (needed by `/speckit.taskstoissues`) | `gh version` |
| 4 | Python 3.11+ | `python3 --version` | (manual — abort if missing) | — |
| 5 | uv | `command -v uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv self update` |
| 6 | Specify CLI (GitHub Spec Kit) | `specify --help` | `uv tool install specify-cli` | `specify self check` then `specify self upgrade` |
| 7 | Spec Kit project files | `.specify/` directory exists | run `specify init --help`, then initialize **in place** in this existing repo with the Claude integration (e.g. `specify init --here --integration claude` or the current equivalent flag) | re-run init after CLI upgrades if templates changed |
| 8 | mattpocock-skills plugin | plugin listed in `claude plugins list` (or `/plugin` UI) | `claude plugins install mattpocock-skills` | auto-updates via official marketplace — verify version |

After installing the plugin, run **`/setup-matt-pocock-skills`** once with: issue tracker = **GitHub**, docs location = **`specs/` + `docs/`**.

**Verify these commands/skills are now available** (abort and report any that are missing):

- Spec Kit: `/speckit.constitution`, `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.analyze`, `/speckit.taskstoissues`, `/speckit.implement`, `/speckit.converge`, `/speckit.checklist`, `/speckit.clarify` (fallback only)
- Pocock: `grill-me`, `grill-with-docs`, `grilling`, `tdd`, `code-review`, `diagnosing-bugs`, `domain-modeling`, `research`, `handoff`, `wizard`, `setup-matt-pocock-skills`

**Disabled by deduplication policy — never use, even though installed:** `/to-spec`, `/to-tickets` (unless tracker is not GitHub), Pocock `/implement`, `/triage`, `/wayfinder`. `/speckit.clarify` only as fallback when grilling was explicitly skipped.

## Step 2 — Materialize the process as .md files

Create this structure (English content, senior-to-senior register: direct, content-dense, no filler):

```
docs/process/
  workflow.md                      # graph, dedupe table, gate modes, compliance articles
  00-profile-and-constitution.md
  01-understand.md
  02-specify.md
  03-constraints.md
  04-architecture.md
  05-tasks.md
  06-implementation.md
  07-review-validate.md
  08-deliver-handover.md
specs/
  PROFILE.md                       # template, see below
CLAUDE.md                          # append process section (create if absent)
```

**`docs/process/workflow.md`** must contain:
1. The phase graph: `0 Profile/Constitution → 1 Understand → 2 Specify → 3 Constraints → 4 Architecture → 5 Tasks → 6 Implementation → 7 Review/Validate → 8 Deliver/Handover`.
2. The binding deduplication table: elicitation = `/grill-with-docs`; spec artifact = `/speckit.specify` (fed by grilling); tasks = `/speckit.tasks` + `/speckit.analyze` gate; issues = `/speckit.taskstoissues`; implementation orchestration = `/speckit.implement` with `/tdd` + `/code-review` mandated per task, one atomic commit per task; drift/brownfield = `/speckit.converge`; handover = `/handoff` + `/wizard` + `CONTEXT.md`/ADRs.
3. Gate modes: `autonomous` (human gates after phases 4 and 7), `standard` (gates after 2, 4, 7), `strict` (gate after every phase). Phases 0–3 are inherently human-in-the-loop (grilling requires the human).
4. Compliance articles, always active regardless of profile: **AVG/GDPR** (privacy by design, data minimization, PII inventory), **NIS2** (risk-based measures, logging/monitoring, incident readiness), **WCAG 2.2 AA** (acceptance criteria on every UI story), **OWASP** (ASVS-aligned requirements, Top 10 in review and validation).

**Each phase file (`00`–`08`)** follows the same schema:
- **Purpose** — one paragraph.
- **Entry criteria** — what must exist before starting.
- **Actions** — exact commands and skills to run, in order.
- **Deliverables** — artifact paths.
- **Exit criteria** — checkable statements (acceptance-style).
- **Transition** — literal last instruction: `On completion, run: bash .workflow/complete-phase.sh <N>` (phase number). Nothing else ends a phase.

**`specs/PROFILE.md`** template fields: `gate_mode: autonomous|standard|strict`, `deliverable_type: proof-of-value|tracer-bullet`, `project_type: greenfield|brownfield`, `tracker: github`. Filled in during Phase 0.

**`CLAUDE.md`** section: role (Senior Lead Dev + PM/PO), core principles (Think First / Specify Second / Code Last; front-loaded autonomy — implementation-time uncertainty means the spec was insufficient: stop, grill, update, resume), pointer to `docs/process/`, the disabled-commands list, and the rule that every phase ends via `complete-phase.sh`.

## Step 3 — State machine + Stop hook (phase chaining)

Create `.workflow/` with:

**`.workflow/state.json`** (initial):
```json
{ "gate_mode": "standard", "last_completed_phase": -1, "gates_approved": [], "last_hook_advance": -1 }
```
`gate_mode` is synced from `specs/PROFILE.md` at the end of Phase 0.

**`.workflow/complete-phase.sh`** — marks phase `$1` complete:
```bash
#!/usr/bin/env bash
set -euo pipefail
S=.workflow/state.json
jq --argjson n "$1" '.last_completed_phase = $n' "$S" > "$S.tmp" && mv "$S.tmp" "$S"
echo "Phase $1 marked complete."
```

**`.workflow/approve-gate.sh`** — human runs this in a terminal to pass a gate:
```bash
#!/usr/bin/env bash
set -euo pipefail
S=.workflow/state.json
jq --argjson n "$1" '.gates_approved |= (. + [$n] | unique)' "$S" > "$S.tmp" && mv "$S.tmp" "$S"
echo "Gate after phase $1 approved. Resume Claude with: continue"
```

**`.workflow/hooks/next-phase.sh`** — the Stop hook. Behavior: if the last completed phase requires a gate that is not yet approved → allow the stop (human acts via `approve-gate.sh`). Otherwise block the stop exactly once per phase and instruct Claude to begin the next phase. Never loop on an unfinished phase.
```bash
#!/usr/bin/env bash
set -euo pipefail
S=.workflow/state.json
[ -f "$S" ] || exit 0
INPUT=$(cat)
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
MODE=$(jq -r '.gate_mode' "$S")
N=$(jq -r '.last_completed_phase' "$S")
ADV=$(jq -r '.last_hook_advance' "$S")
NEXT=$((N + 1))
[ "$N" -lt 0 ] && exit 0          # nothing completed yet
[ "$NEXT" -gt 8 ] && exit 0       # workflow finished
case "$MODE" in
  autonomous) GATES="4 7" ;;
  standard)   GATES="2 4 7" ;;
  strict)     GATES="0 1 2 3 4 5 6 7" ;;
  *)          GATES="0 1 2 3 4 5 6 7" ;;  # fail safe: strict
esac
if echo " $GATES " | grep -q " $N " && ! jq -e --argjson n "$N" '.gates_approved | index($n)' "$S" >/dev/null; then
  exit 0                          # gate pending: allow stop, human approves via approve-gate.sh
fi
if [ "$ADV" = "$N" ] && [ "$ACTIVE" = "true" ]; then
  exit 0                          # already advanced for this phase once: no loops
fi
jq --argjson n "$N" '.last_hook_advance = $n' "$S" > "$S.tmp" && mv "$S.tmp" "$S"
FILE=$(ls docs/process/0${NEXT}-*.md 2>/dev/null | head -1)
cat <<JSON
{"decision":"block","reason":"Phase ${N} complete. Begin Phase ${NEXT}: read ${FILE} and execute it exactly. End the phase only via: bash .workflow/complete-phase.sh ${NEXT}"}
JSON
```
`chmod +x` all three scripts.

**Register the hook** — merge into `.claude/settings.json` (create if absent, preserve existing keys):
```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "bash .workflow/hooks/next-phase.sh" } ] }
    ]
  }
}
```

## Step 4 — Wire the loop

Confirm every phase file `00`–`08` ends with its `complete-phase.sh <N>` transition line, and that `CLAUDE.md` states: phases end **only** via `complete-phase.sh`; the Stop hook decides whether the next phase starts automatically (per gate mode) or waits for `approve-gate.sh`.

## Step 5 — Self-check & commit

1. Print a status table: component versions (Step 1), generated files (Steps 2–3), hook registration confirmed, executable bits on scripts.
2. Dry-run the hook: `echo '{"stop_hook_active":false}' | bash .workflow/hooks/next-phase.sh` with `last_completed_phase:-1` — must exit silently.
3. Commit everything: `chore: bootstrap agent workflow graph process` (English, conventional commits).
4. Tell the user the next action: **start Phase 0** — fill `specs/PROFILE.md`, run `/speckit.constitution` (five pillars, engineering baseline incl. TDD + two-axis review + atomic commits, and the four compliance articles), then `bash .workflow/complete-phase.sh 0`.
