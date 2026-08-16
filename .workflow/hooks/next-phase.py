#!/usr/bin/env python3
"""Stop hook: chain the workflow from one phase into the next.

Blocks the stop exactly once per completed phase and tells Claude to start the
next one, on the model that phase is routed to. Every other stop is left
alone, which matters for two reasons: a session must stay usable for ordinary
questions mid-phase, and the retro Stop hook in the shared config only fires
on a stop that nobody else blocked.

Order of decisions, all of which end in a silent exit 0:

  1. Another hook already blocked this turn (stop_hook_active) -> yield.
  2. No state file, or nothing completed yet, or the graph is finished.
  3. The completed phase has a gate that the human has not approved yet.
  4. We already advanced once for this completed phase.
  5. The session runs the wrong model for the next phase: stall, once. The
     block tells Claude to have the human switch models; the phase does not
     start, and it never starts on a lighter model instead. This is also the
     safe pause point when a usage limit ran out mid-window.

Only when none of those hold does it print a block decision, now naming the
model the phase is routed to (read from the phase file's frontmatter via
.workflow/routing.py, never defined here). When the session model cannot be
read from the transcript the hook fails open and advances, because a broken
guard must never wedge a session; the block text still names the required
model so the session can refuse the phase itself.

Any unexpected failure exits 0 and silent, for the same reason.
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE = ROOT / ".workflow" / "state.json"
PHASE_DOCS = ROOT / "docs" / "process"
LAST_PHASE = 8
GATES = {"autonomous": {4, 7}, "standard": {2, 4, 7}}
STRICT = set(range(LAST_PHASE))

sys.path.insert(0, str(ROOT / ".workflow"))
try:
    import routing
except Exception:  # a project without routing.py chains phases unrouted
    routing = None


def skip():
    sys.exit(0)


def required_model(phase):
    if routing is None:
        return None
    try:
        return routing.resolve_phase(phase)
    except Exception:
        return None


def current_model(payload):
    if routing is None:
        return None
    try:
        return routing.session_model(payload.get("transcript_path"))
    except Exception:
        return None


def write_state(state):
    tmp = STATE.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # 1. Someone else already blocked this stop. Do not pile on.
    if payload.get("stop_hook_active"):
        skip()

    if not STATE.is_file():
        skip()
    try:
        with STATE.open() as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        skip()

    completed = state.get("last_completed_phase", -1)
    if not isinstance(completed, int) or completed < 0:
        skip()  # 2. nothing finished yet
    nxt = completed + 1
    if nxt > LAST_PHASE:
        skip()  # graph finished

    # 3. Pending human gate: allow the stop so the human can run approve-gate.py.
    mode = state.get("gate_mode", "strict")
    gates = GATES.get(mode, STRICT)
    if completed in gates and completed not in state.get("gates_approved", []):
        skip()

    # 4. Advance once per completed phase, whatever happens in between.
    if state.get("last_hook_advance") == completed:
        skip()

    # 5. Wrong model for the next phase: stall instead of advancing, and say so
    # exactly once. The phase starts when the session runs the required model;
    # it never starts on a substitute.
    required = required_model(nxt)
    current = current_model(payload)
    if required and current and current != required:
        if state.get("last_model_stall") == completed:
            skip()
        state["last_model_stall"] = completed
        try:
            write_state(state)
        except OSError:
            skip()
        reason = (
            f"Phase {completed} is complete, but phase {nxt} is routed to {required} and this "
            f"session is running on {current}. Do not begin phase {nxt} on this model, and never "
            f"substitute a lighter one. Tell the user to switch with `/model {required}` (or to "
            f"reopen the session on that model) and then say continue. If a usage limit was just "
            f"hit, pausing here and resuming later on {required} is the correct move; downgrading "
            f"is not."
        )
        json.dump({"decision": "block", "reason": reason}, sys.stdout)
        sys.exit(0)

    state["last_hook_advance"] = completed
    try:
        write_state(state)
    except OSError:
        skip()  # cannot record the advance, so do not advance at all

    matches = sorted(PHASE_DOCS.glob(f"{nxt:02d}-*.md"))
    if not matches:
        skip()
    doc = matches[0].relative_to(ROOT)

    routed = ""
    if required:
        routed = (
            f" This phase is routed to {required}; if this session is not running that model, "
            f"stop and ask the user to switch with `/model {required}` before doing any phase work."
        )
    reason = (
        f"Phase {completed} is complete. Begin phase {nxt}: read {doc} and execute it exactly."
        f"{routed} "
        f"End the phase only with: python3 .workflow/complete-phase.py {nxt}"
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
