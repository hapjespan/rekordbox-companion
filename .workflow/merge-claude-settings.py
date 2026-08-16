#!/usr/bin/env python3
"""Merge the workflow's required settings into an existing .claude/settings.json.

    python3 .workflow/merge-claude-settings.py .claude/settings.json \
        --from .workflow/required-settings.json [--dry-run]

Two moments need this and both used to be a paragraph of prose telling somebody
to merge carefully by hand:

  * kickoff, when the cloned repository already ships a .claude/settings.json;
  * /start-project, because `specify init` rewrites that file and drops whatever
    the scaffold put there.

The merge only ever adds:

  hooks               a group is appended unless its command is already
                      registered on that event
  enabledPlugins      a plugin is added only when the target has no opinion, so
                      a local decision to switch one off survives
  permissions.deny    union, order preserved, duplicates dropped
  anything else       copied only when the key is absent

Nothing is removed or overwritten, so running it twice changes nothing the
second time. Keys starting with `_` are treated as comments and skipped.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys


def load(path, what):
    try:
        with path.open() as fh:
            data = json.load(fh)
    except FileNotFoundError:
        if what == "target":
            return {}
        sys.exit(f"{path} does not exist")
    except ValueError as exc:
        sys.exit(f"{path} is not valid JSON ({exc}). Fix it by hand; refusing to overwrite.")
    if not isinstance(data, dict):
        sys.exit(f"{path} is not a JSON object")
    return data


def merge_hooks(target, wanted, changes):
    for event, groups in wanted.items():
        existing = target.setdefault("hooks", {}).setdefault(event, [])
        registered = {
            hook.get("command")
            for group in existing
            for hook in group.get("hooks", [])
        }
        for group in groups:
            commands = [hook.get("command") for hook in group.get("hooks", [])]
            if any(command in registered for command in commands):
                continue
            existing.append(group)
            changes.append(f"hook {event}: {', '.join(str(c) for c in commands)}")


def merge_plugins(target, wanted, changes):
    current = target.setdefault("enabledPlugins", {})
    for name, value in wanted.items():
        if name in current:
            continue
        current[name] = value
        changes.append(f"plugin {name} = {json.dumps(value)}")


def merge_permissions(target, wanted, changes):
    current = target.setdefault("permissions", {})
    for bucket, rules in wanted.items():
        if not isinstance(rules, list):
            if bucket not in current:
                current[bucket] = rules
                changes.append(f"permissions.{bucket}")
            continue
        have = current.setdefault(bucket, [])
        for rule in rules:
            if rule not in have:
                have.append(rule)
                changes.append(f"permissions.{bucket}: {rule}")


def merge(target, wanted):
    changes = []
    for key, value in wanted.items():
        if key.startswith("_"):
            continue
        if key == "hooks":
            merge_hooks(target, value, changes)
        elif key == "enabledPlugins":
            merge_plugins(target, value, changes)
        elif key == "permissions":
            merge_permissions(target, value, changes)
        elif key not in target:
            target[key] = value
            changes.append(f"{key}")
    return changes


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", type=pathlib.Path, help="the settings.json to merge into")
    parser.add_argument("--from", dest="source", type=pathlib.Path, required=True,
                        help="the settings this workflow requires")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    target = load(args.target, "target")
    wanted = load(args.source, "source")

    changes = merge(target, wanted)
    if not changes:
        print(f"{args.target}: already has everything it needs")
        return 0

    for change in changes:
        print(f"adding: {change}")

    if args.dry_run:
        print(f"--dry-run: {len(changes)} change(s) not written")
        return 0

    if args.target.exists():
        shutil.copy2(args.target, args.target.with_suffix(".json.bak"))
        print(f"backup: {args.target.with_suffix('.json.bak')}")
    args.target.parent.mkdir(parents=True, exist_ok=True)

    tmp = args.target.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(target, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, args.target)
    print(f"updated {args.target}: {len(changes)} change(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
