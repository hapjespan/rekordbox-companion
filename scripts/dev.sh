#!/bin/sh
# Launches the FastAPI backend (auto-reload) and the Vite dev proxy together,
# and tears both down on Ctrl+C: without the trap, backgrounding uvicorn on
# its own line would orphan it once the foreground job exits (phase 6, T005
# review finding).
#
# Takes the base uvicorn invocation as $1 so the Makefile's UVICORN variable
# stays the single source of truth shared with `make run` (T005).
set -e

if [ -z "$1" ]; then
  echo "usage: $0 '<uvicorn base command>' (see the Makefile's UVICORN variable)" >&2
  exit 1
fi
UVICORN_CMD="$1"

cd "$(dirname "$0")/.."

trap 'kill 0' EXIT INT TERM

(cd engine && $UVICORN_CMD --reload) &
(cd web && pnpm dev) &

wait
