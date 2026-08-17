.PHONY: setup dev test build run

UVICORN = uv run uvicorn companion.main:app --host 127.0.0.1 --port 8787

setup:
	cd engine && uv sync
	cd web && pnpm install
	cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit

dev:
	trap 'kill 0' EXIT INT TERM; \
	(cd engine && $(UVICORN) --reload) & \
	(cd web && pnpm dev) & \
	wait

test:
	cd engine && uv run pytest
	cd web && pnpm test

build:
	cd web && pnpm build

run:
	cd engine && $(UVICORN)
