#!/usr/bin/env python3
"""Mark a workflow phase complete. This is the only thing that ends a phase.

    python3 .workflow/complete-phase.py <0-8> [--force]

Phases must complete in order; --force overrides that, which is what a
brownfield project needs when it enters the graph halfway. --force also skips
the routing checks below, for the same reason: work done outside the graph has
no ledger.

Phases 5 to 7 only complete when their model-routing evidence exists: a valid
task list with valid complexity flags (5), a recorded builder per task (6), a
recorded reviewer per task who is not its builder (7). The checks live in
routing.py; this script refuses to mark the phase until they pass, which is
what turns the routing policy from documentation into a property of the
state machine.

Written in python3 without third-party modules on purpose: python3 is the only
interpreter present on the host and in every project container, and jq is not.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import routing

STATE = pathlib.Path(__file__).resolve().parent / "state.json"
LAST_PHASE = 8


def load():
    try:
        with STATE.open() as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"{STATE} does not exist. Run /start-project first.")
    except json.JSONDecodeError as exc:
        sys.exit(f"{STATE} is not valid JSON ({exc}). Fix it by hand; refusing to overwrite.")


def save(state):
    """Write through a temp file so a crash cannot leave a truncated state."""
    tmp = STATE.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", type=int, help=f"phase number, 0 to {LAST_PHASE}")
    parser.add_argument("--force", action="store_true", help="allow completing out of order")
    args = parser.parse_args()

    if not 0 <= args.phase <= LAST_PHASE:
        sys.exit(f"phase must be between 0 and {LAST_PHASE}, got {args.phase}")

    state = load()
    previous = state.get("last_completed_phase", -1)
    if not args.force and args.phase != previous + 1:
        sys.exit(
            f"phase {args.phase} is out of order: last completed is {previous}, "
            f"so {previous + 1} comes next. Use --force to override."
        )

    if args.force:
        try:
            skipped = bool(routing.boundary_problems(args.phase))
        except routing.RoutingError:
            skipped = True
        if skipped:
            print("routing checks skipped by --force; the model ledger is incomplete for this phase")
    else:
        try:
            problems = routing.boundary_problems(args.phase)
        except routing.RoutingError as exc:
            sys.exit(f"phase {args.phase} is not complete: {exc}")
        if problems:
            sys.exit(
                f"phase {args.phase} is not complete; its routing evidence is missing:\n  - "
                + "\n  - ".join(problems)
            )

    state["last_completed_phase"] = args.phase
    save(state)
    print(f"Phase {args.phase} marked complete.")

    mode = state.get("gate_mode", "strict")
    gates = {"autonomous": {4, 7}, "standard": {2, 4, 7}}.get(mode, set(range(LAST_PHASE)))
    if args.phase in gates and args.phase not in state.get("gates_approved", []):
        print(
            f"A gate follows phase {args.phase} in {mode} mode. "
            f"Approve it with: python3 .workflow/approve-gate.py {args.phase}"
        )
    elif args.phase == LAST_PHASE:
        print("That was the last phase. The workflow is complete.")


if __name__ == "__main__":
    main()
