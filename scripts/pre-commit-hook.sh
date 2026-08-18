#!/bin/sh
# Installed into .git/hooks/pre-commit by `make setup`. Keeps the two lint
# gates (ruff, eslint/prettier) from drifting onto main by mistake; CI is not
# wired up yet (project rule 7, phase-per-PR), so this is the only gate today.
set -e

if [ -f engine/pyproject.toml ]; then
  (cd engine && uv run ruff check . && uv run ruff format --check .)
fi

if [ -f web/package.json ]; then
  (cd web && pnpm run lint && pnpm run format:check)
fi
