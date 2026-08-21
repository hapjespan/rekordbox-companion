#!/bin/sh
# Installed into .git/hooks/pre-commit by `make setup`. Keeps the two lint
# gates (ruff, eslint/prettier) from drifting onto main by mistake; CI is not
# wired up yet (project rule 7, phase-per-PR), so this is the only gate today.
set -e

if git diff --cached --name-only | grep -q '\.pnpm-store/'; then
  echo "Refusing commit: staged files under .pnpm-store/. This is pnpm's" >&2
  echo "content-addressable store, never intended content; a .gitignore that" >&2
  echo "lacks this entry on some branch is not a reason to commit it." >&2
  exit 1
fi

if [ -f engine/pyproject.toml ]; then
  (cd engine && uv run ruff check . && uv run ruff format --check .)
fi

if [ -f web/package.json ]; then
  (cd web && pnpm run lint && pnpm run format:check)
fi
