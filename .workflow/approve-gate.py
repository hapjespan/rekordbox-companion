#!/usr/bin/env python3
"""Approve the human gate that follows a phase.

    python3 .workflow/approve-gate.py <0-8>

Run this yourself, in a terminal. Claude cannot approve its own gate: the whole
point of a gate is that a human looked at the deliverables of that phase.

That sentence used to be the entire enforcement, which made the gate a comment
addressed to whoever read the file. Two mechanisms back it up now:

  1. This script requires a terminal. A human runs `docker exec -it`, which gives
     one; an agent's shell has no tty. This is the check that survives `docker
     exec` from the host, which does not forward the environment.
  2. It also refuses when it detects an agent session (CLAUDECODE is set in every
     shell Claude Code spawns). Override both with WORKFLOW_GATE_HUMAN=1 only if
     you are a human whose terminal genuinely lacks a tty.
  3. The project's .claude/settings.json denies the Bash calls that would invoke
     this script, so the attempt is refused before it reaches python.

Neither is a sandbox: an agent that sets out to defeat them can. They exist to
stop the far more likely case, an agent that approves its own gate while trying
to be helpful, and to make a deliberate bypass visible in the transcript.
"""
import argparse
import json
import os
import pathlib
import sys

STATE = pathlib.Path(__file__).resolve().parent / "state.json"
LAST_PHASE = 8
GATES = {"autonomous": {4, 7}, "standard": {2, 4, 7}}

AGENT_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")


HUMAN_ADVICE = (
    "A gate means a human looked at the deliverables of that phase. Open a "
    "terminal in this container and run it there:\n"
    "    docker exec -it <project>-dev python3 .workflow/approve-gate.py <N>"
)


def refuse_if_agent():
    if os.environ.get("WORKFLOW_GATE_HUMAN") == "1":
        return

    present = [name for name in AGENT_MARKERS if os.environ.get(name)]
    if present:
        sys.exit(
            "Refusing to approve a gate from an agent session "
            f"({', '.join(present)} set in the environment).\n" + HUMAN_ADVICE
        )

    # docker exec does not forward the host environment, so an agent on the host
    # reaches this script with none of the markers set. It does not get a tty.
    if not sys.stdin.isatty():
        sys.exit(
            "Refusing to approve a gate without a terminal.\n" + HUMAN_ADVICE
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", type=int, help=f"the phase the gate follows, 0 to {LAST_PHASE}")
    args = parser.parse_args()

    if not 0 <= args.phase <= LAST_PHASE:
        sys.exit(f"phase must be between 0 and {LAST_PHASE}, got {args.phase}")

    refuse_if_agent()

    try:
        with STATE.open() as fh:
            state = json.load(fh)
    except FileNotFoundError:
        sys.exit(f"{STATE} does not exist. Run /start-project first.")
    except json.JSONDecodeError as exc:
        sys.exit(f"{STATE} is not valid JSON ({exc}). Fix it by hand; refusing to overwrite.")

    mode = state.get("gate_mode", "strict")
    gates = GATES.get(mode, set(range(LAST_PHASE)))
    if args.phase not in gates:
        print(f"Note: {mode} mode has no gate after phase {args.phase}. Recording it anyway.")

    approved = sorted(set(state.get("gates_approved", [])) | {args.phase})
    state["gates_approved"] = approved
    tmp = STATE.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE)

    print(f"Gate after phase {args.phase} approved. Resume Claude with: continue")


if __name__ == "__main__":
    main()
