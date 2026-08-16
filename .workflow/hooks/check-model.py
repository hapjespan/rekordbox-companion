#!/usr/bin/env python3
"""UserPromptSubmit hook: flag a session doing phase work on the wrong model.

The Stop hook refuses to start a phase on the wrong model, but a session can
still drift mid-phase: a usage limit hits, someone reopens the project on
whatever model the terminal had, and phase 7 quietly continues on a lighter
model. This hook closes that hole. On every prompt it compares the phase in
progress (from .workflow/state.json) with the model of the last assistant
message in the transcript; on a mismatch it injects one line of context so the
session stops phase work and asks for the switch, instead of downgrading.

It prints nothing when everything matches, when no phase is in progress, or
when it cannot tell, and it exits 0 always: a broken guard must never block a
prompt. The last assistant message can be stale for exactly one turn after a
/model switch, so the injected line says how to recognise that.

The routing itself lives in configuration (phase frontmatter, the profile,
the agent files); this hook defines no model name, it only reads routing.py.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(ROOT / ".workflow"))


def main():
    try:
        import routing
    except Exception:
        return

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    try:
        phase = routing.phase_in_progress()
        if phase is None:
            return
        required = routing.resolve_phase(phase)
        current = routing.session_model(payload.get("transcript_path"))
    except Exception:
        return

    if not required or not current or current == required:
        return

    print(
        f"workflow model check: phase {phase} is routed to {required}, but this session's last "
        f"reply came from {current}. If the user just switched with /model and you are {required} "
        f"yourself, this notice is stale for one turn; ignore it. Otherwise do no phase-{phase} "
        f"work: tell the user to run /model {required} and wait. Never downgrade a phase to a "
        f"lighter model; after a usage limit, pause and resume on the required model."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
