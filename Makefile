.PHONY: setup dev test build run

# DEV_HOST lets the containerized dev environment bind 0.0.0.0 (docker-compose.yml
# sets it), while the real target -- the DJ's Mac, no container, no extra network
# namespace hop -- keeps the documented 127.0.0.1-only default. Binding the
# in-container process to 127.0.0.1 is unreachable through Docker's published
# port: the port mapping delivers traffic to the container's own network
# interface, not its loopback.
UVICORN = uv run uvicorn companion.main:app --host $${DEV_HOST:-127.0.0.1} --port 8787

setup:
	cd engine && uv sync
	cd engine && uv run alembic upgrade head
	cd web && pnpm install
	cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit

dev:
	./scripts/dev.sh "$(UVICORN)"

test:
	cd engine && uv run pytest
	cd web && pnpm test

build:
	cd web && pnpm build

run:
	cd engine && $(UVICORN)
