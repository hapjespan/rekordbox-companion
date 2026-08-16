#!/usr/bin/env python3
"""Model routing for the Agent Workflow Graph: which model runs what, enforced.

    python3 .workflow/routing.py phase 6          # model for a phase
    python3 .workflow/routing.py current          # model for the phase in progress
    python3 .workflow/routing.py task T012        # model that builds one task
    python3 .workflow/routing.py record-build T012 <model>
    python3 .workflow/routing.py record-review T012 <model>
    python3 .workflow/routing.py check 6          # boundary check, used by complete-phase
    python3 .workflow/routing.py doctor           # resolve everything, exit 1 on gaps

Routing lives in configuration, never in code. Each phase file under
docs/process/ pins its model in frontmatter; specs/PROFILE.md may override one
phase with a `model_phase_<N>:` line; the subagents under .claude/agents/ pin
the models for gate reviews, escalated tasks and bulk mechanical text. This
script only reads those places and contains no model name of its own. The
tests in the claude-config repository hold that configuration to the routing
policy, so drift fails CI instead of burning the usage limit quietly.

Three rules are enforced mechanically rather than documented:

  * Escalation is explicit. A task builds on the escalation model only when
    tasks.md flags it `[complexity: high]`; a missing flag means standard, an
    invalid flag is an error, never silently standard. The orchestrator may
    propose an escalation, but it happens by editing tasks.md first, so the
    diff is the audit trail. record-build refuses anything else.
  * The model that built a task never reviews it. record-review refuses a
    reviewer equal to the recorded builder, and `check 7` re-verifies it.
  * A phase is only complete when its routing evidence exists: `check 5`
    demands a valid task list, `check 6` a recorded builder per task,
    `check 7` a recorded reviewer per task. complete-phase.py runs these
    before it marks anything complete.

Written in python3 without third-party modules on purpose, like the rest of
.workflow: python3 is the only interpreter present everywhere, and pyyaml is
not, which is why the frontmatter parser below only reads flat `key: value`.
"""
import argparse
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = pathlib.Path(__file__).resolve().parent / "model-ledger.json"
STATE = pathlib.Path(__file__).resolve().parent / "state.json"
LAST_PHASE = 8

VALID_COMPLEXITY = ("standard", "high")
ESCALATION_AGENT = "task-builder-high"
GATE_REVIEW_AGENT = "gate-review"
SCRIBE_AGENT = "scribe"

TASK_LINE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(?:\*\*)?(T\d+)")
COMPLEXITY = re.compile(r"\[complexity:\s*([A-Za-z-]+)\s*\]")


class RoutingError(Exception):
    """A routing decision a human or the orchestrator has to fix. Never a trace."""


# --------------------------------------------------------------------------- #
# Configuration readers: frontmatter, profile, agents
# --------------------------------------------------------------------------- #

def frontmatter(path):
    """The flat `key: value` block between two --- lines at the top of a file."""
    try:
        lines = path.read_text().splitlines()
    except (OSError, AttributeError):
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    data = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        key, sep, value = line.partition(":")
        if sep:
            data[key.strip()] = value.strip()
    return {}


def phase_doc(phase):
    matches = sorted((ROOT / "docs" / "process").glob(f"{phase:02d}-*.md"))
    return matches[0] if matches else None


def profile_override(phase):
    try:
        text = (ROOT / "specs" / "PROFILE.md").read_text()
    except OSError:
        return None
    match = re.search(rf"^model_phase_{phase}:[ \t]*(\S+)", text, re.M)
    return match.group(1) if match else None


def resolve_phase(phase):
    """The model a phase runs on: a profile override wins, else the frontmatter."""
    override = profile_override(phase)
    if override:
        return override
    model = frontmatter(phase_doc(phase) or pathlib.Path()).get("model")
    if not model:
        raise RoutingError(
            f"no model configured for phase {phase}: expected `model:` in the "
            f"frontmatter of docs/process/{phase:02d}-*.md"
        )
    return model


def agent_model(name):
    path = ROOT / ".claude" / "agents" / f"{name}.md"
    model = frontmatter(path).get("model")
    if not model:
        raise RoutingError(
            f"{path.relative_to(ROOT) if path.is_absolute() else path} is missing "
            "or has no `model:` frontmatter; the routing depends on it"
        )
    return model


# --------------------------------------------------------------------------- #
# Tasks and their complexity flags
# --------------------------------------------------------------------------- #

def tasks_files():
    specs = ROOT / "specs"
    return sorted(specs.glob("**/tasks.md")) if specs.is_dir() else []


def read_tasks():
    """task id -> raw complexity marker, None when the line carries no marker."""
    tasks = {}
    for path in tasks_files():
        for line in path.read_text().splitlines():
            match = TASK_LINE.match(line)
            if not match:
                continue
            marker = COMPLEXITY.search(line)
            tasks[match.group(1)] = marker.group(1).lower() if marker else None
    return tasks


def complexity_of(task_id, tasks=None):
    tasks = read_tasks() if tasks is None else tasks
    if task_id not in tasks:
        raise RoutingError(f"{task_id} does not appear as a task line in any specs/**/tasks.md")
    marker = tasks[task_id]
    if marker is None:
        return "standard"
    if marker not in VALID_COMPLEXITY:
        raise RoutingError(
            f"{task_id} carries complexity `{marker}`, which is not one of: "
            f"{', '.join(VALID_COMPLEXITY)}. Fix the flag in tasks.md; an invalid "
            "value is an error, never silently standard."
        )
    return marker


def task_model(task_id):
    if complexity_of(task_id) == "high":
        return agent_model(ESCALATION_AGENT)
    return resolve_phase(6)


# --------------------------------------------------------------------------- #
# The ledger: who built and who reviewed each task
# --------------------------------------------------------------------------- #

def load_ledger():
    try:
        with LEDGER.open() as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RoutingError(
            f"{LEDGER} is not valid JSON ({exc}). Fix it by hand; refusing to overwrite."
        )


def save_ledger(ledger):
    tmp = LEDGER.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, LEDGER)


def record_build(task_id, model):
    expected = task_model(task_id)
    if model != expected:
        if complexity_of(task_id) == "standard" and model == agent_model(ESCALATION_AGENT):
            raise RoutingError(
                f"{task_id} is not flagged high, so it does not build on {model}. "
                "Escalation is explicit: set `[complexity: high]` on the task line in "
                "tasks.md with the reason, commit that, then build. The flag is the "
                "single source of truth; the orchestrator only proposes."
            )
        raise RoutingError(
            f"{task_id} is `{complexity_of(task_id)}` and builds on {expected}, not {model}."
        )
    ledger = load_ledger()
    ledger.setdefault(task_id, {})["built_by"] = model
    save_ledger(ledger)
    print(f"{task_id}: built by {model}, recorded.")


def record_review(task_id, model):
    ledger = load_ledger()
    builder = ledger.get(task_id, {}).get("built_by")
    if not builder:
        raise RoutingError(f"{task_id} has no recorded builder; record the build before the review.")
    if model == builder:
        hint = ""
        if resolve_phase(7) == builder:
            hint = (
                " Phase 7 is currently configured to run on that same model; fix the "
                "routing (the profile override or the task's complexity flag) so a "
                "different model can review this task."
            )
        raise RoutingError(
            f"{task_id} was built by {builder}, and the model that implemented a task "
            f"never reviews it.{hint}"
        )
    expected = resolve_phase(7)
    if model != expected:
        raise RoutingError(f"phase 7 reviews run on {expected}, not {model}.")
    ledger.setdefault(task_id, {})["reviewed_by"] = model
    save_ledger(ledger)
    print(f"{task_id}: reviewed by {model}, recorded.")


# --------------------------------------------------------------------------- #
# Phase boundaries: what complete-phase.py demands before it marks anything
# --------------------------------------------------------------------------- #

def boundary_problems(phase):
    """What stands between this phase and complete. An empty list means go."""
    if phase not in (5, 6, 7):
        return []
    if not tasks_files():
        return [f"no specs/**/tasks.md exists, and phase {phase} is judged against the task list"]
    tasks = read_tasks()
    if not tasks:
        return ["the task files contain no task lines (`- [ ] Tnnn ...`)"]

    problems = []
    for task_id in sorted(tasks):
        try:
            complexity_of(task_id, tasks)
        except RoutingError as exc:
            problems.append(str(exc))
    if phase == 5 or problems:
        return problems

    ledger = load_ledger()
    for task_id in sorted(tasks):
        built = ledger.get(task_id, {}).get("built_by")
        if not built:
            problems.append(
                f"{task_id} has no recorded builder: "
                f"python3 .workflow/routing.py record-build {task_id} <model>"
            )
            continue
        if phase == 7:
            reviewed = ledger.get(task_id, {}).get("reviewed_by")
            if not reviewed:
                problems.append(
                    f"{task_id} has no recorded reviewer: "
                    f"python3 .workflow/routing.py record-review {task_id} <model>"
                )
            elif reviewed == built:
                problems.append(
                    f"{task_id} was reviewed by the model that built it ({built}); "
                    "that review does not count"
                )
    return problems


# --------------------------------------------------------------------------- #
# Shared helper for the hooks: which model is this session actually running?
# --------------------------------------------------------------------------- #

def session_model(transcript_path, tail_bytes=65536):
    """The model of the last assistant message in a session transcript.

    Reads only the tail of the file because transcripts grow to megabytes.
    Returns None whenever the answer is not certain; callers treat None as
    "do not enforce", because a guard that guesses is worse than no guard.
    """
    try:
        path = pathlib.Path(transcript_path)
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - tail_bytes))
            tail = fh.read().decode("utf-8", errors="replace")
    except (OSError, TypeError, ValueError):
        return None
    for line in reversed(tail.splitlines()):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("type") == "assistant":
            model = entry.get("message", {}).get("model")
            if isinstance(model, str) and model:
                return model
    return None


def phase_in_progress():
    """The phase the graph is currently in, or None outside the graph."""
    try:
        with STATE.open() as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    completed = state.get("last_completed_phase", -1)
    if not isinstance(completed, int) or completed >= LAST_PHASE:
        return None
    nxt = completed + 1
    if completed >= 0 and state.get("last_hook_advance") != completed:
        # The next phase has not been started by the machine yet: a gate may be
        # pending, or the session stalled on a model switch. Nothing in progress.
        return None
    return nxt


# --------------------------------------------------------------------------- #

def doctor():
    """Resolve the whole routing table and refuse to bless a broken one."""
    failures = 0
    print("phase routing (profile override > phase frontmatter):")
    for phase in range(LAST_PHASE + 1):
        try:
            origin = "profile" if profile_override(phase) else "frontmatter"
            print(f"  phase {phase}: {resolve_phase(phase)}  [{origin}]")
        except RoutingError as exc:
            failures += 1
            print(f"  phase {phase}: ERROR {exc}")
    print("agents (.claude/agents/):")
    for name, job in (
        (GATE_REVIEW_AGENT, "gate reviews, every gate mode"),
        (ESCALATION_AGENT, "tasks flagged [complexity: high]"),
        (SCRIBE_AGENT, "bulk mechanical text"),
    ):
        try:
            print(f"  {name}: {agent_model(name)}  [{job}]")
        except RoutingError as exc:
            failures += 1
            print(f"  {name}: ERROR {exc}")
    print(f"ledger: {LEDGER if LEDGER.is_file() else 'not created yet (first record-build creates it)'}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_phase = sub.add_parser("phase", help="print the model a phase runs on")
    p_phase.add_argument("number", type=int)
    sub.add_parser("current", help="print the model for the phase in progress")
    p_task = sub.add_parser("task", help="print the model that builds a task")
    p_task.add_argument("task_id")
    p_build = sub.add_parser("record-build", help="record which model built a task")
    p_build.add_argument("task_id")
    p_build.add_argument("model")
    p_review = sub.add_parser("record-review", help="record which model reviewed a task")
    p_review.add_argument("task_id")
    p_review.add_argument("model")
    p_check = sub.add_parser("check", help="boundary check for a phase; exit 1 on problems")
    p_check.add_argument("number", type=int)
    sub.add_parser("doctor", help="resolve the whole table, exit 1 on gaps")
    args = parser.parse_args()

    try:
        if args.command == "phase":
            if not 0 <= args.number <= LAST_PHASE:
                raise RoutingError(f"phase must be between 0 and {LAST_PHASE}, got {args.number}")
            print(resolve_phase(args.number))
        elif args.command == "current":
            phase = phase_in_progress()
            if phase is None:
                raise RoutingError("no phase is in progress")
            print(resolve_phase(phase))
        elif args.command == "task":
            print(task_model(args.task_id))
        elif args.command == "record-build":
            record_build(args.task_id, args.model)
        elif args.command == "record-review":
            record_review(args.task_id, args.model)
        elif args.command == "check":
            problems = boundary_problems(args.number)
            for problem in problems:
                print(problem)
            if problems:
                return 1
            print(f"phase {args.number}: routing evidence complete")
        elif args.command == "doctor":
            return doctor()
    except RoutingError as exc:
        sys.exit(f"routing: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
