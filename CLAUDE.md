# rekordbox-companion

Local-first web app for a working DJ: match Spotify playlists against the local
Rekordbox collection, write matches back as Rekordbox playlists (guarded, with
backups), link missing tracks to the Apple Music / iTunes Store, and generate
booking-type playlist structures. Full brief and decision log: `specs/kickoff.md`.

## Context

- Personal project: code is hosted on GitHub under Martien's own account.
- Indicia work projects are never developed in this environment; they belong on the Indicia work laptop (Mac).

## Environment

- Runs in its own container, code mounted at /workspace/rekordbox-companion.
- Database: PostgreSQL database "rekordbox-companion" on host "postgres" (central container on dev-net). Redis on host "redis". Credentials in .env (never commit).
- Global conventions and the knowledge base workflow are defined in ~/.claude/CLAUDE.md and apply here.

## Tech stack

One-off stack, not the standard nextjs/laravel scaffold (see `specs/kickoff.md`
section 5 for the full table):

- Backend: Python 3.12, FastAPI, uvicorn in `engine/` (uv-managed; the image
  ships uv, not Python 3.12 itself). pyrekordbox for `master.db`, rapidfuzz for
  matching, SQLite via SQLAlchemy 2.x + Alembic for own data.
- Frontend: React 18, TypeScript, Vite, Tailwind v4 in `web/` (pnpm via corepack).
- ffmpeg is in the image for the audio transcode fallback.
- The central Postgres database `rekordbox-companion` exists but is unused in v1;
  it is reserved for the P2 read-only analytics mirror.
- The app itself binds to 127.0.0.1:8787 and ultimately runs on the DJ's Mac,
  where the real Rekordbox 7.2.17 and `master.db` live. Development here runs
  against a fixture copy of `master.db`; anything needing the real install
  (SQLCipher key, `/api/health` version match) is verified on the Mac.

## Coding conventions

- Code, comments, commit messages, branch names and documentation in English;
  UI copy in Dutch.
- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).
- Lint with ruff in `engine/` and ESLint + Prettier in `web/`; a change is not
  done until both pass.
- Test-driven discipline: write the failing test first. Golden matching
  fixtures are append-only — extend them, never weaken one to make a change pass.
- Small, verifiable steps; run the relevant tests or a build check before
  declaring work done.
- Never commit secrets; `.env` stays out of git, keep `env.example` current.

## Build commands

Real `Makefile` targets, verified against `engine/pyproject.toml` and
`web/package.json`:

- `make setup` — `uv sync` in `engine/`, `pnpm install` in `web/`, installs the
  repo's pre-commit hook.
- `make dev` — runs both dev servers together via `scripts/dev.sh`.
- `make test` — `pytest` in `engine/`, `pnpm test` (vitest) in `web/`.
- `make build` — `pnpm build` in `web/`.
- `make run` — starts uvicorn (`companion.main:app`) on 127.0.0.1:8787.

## Implementation confidence threshold

Implement only at >= 95 percent confidence in the specification and approach;
below that stop, ask the question, and record the answer in the spec or an ADR
before writing code.

## Index

Pointers, not copies — read the linked file for the actual content:

- `docs/HANDOVER.md` — phase 8 handover: start here if you were not in the room.
- `specs/` — the kickoff brief and decision log (`kickoff.md`) and the project
  profile (`PROFILE.md`: gate mode, risk class, deploy target). Read before
  any spec-level question.
- `docs/adr/` — architecture decision records; see `docs/adr/README.md` for the
  filename format and what belongs in one.
- `docs/process/workflow.md` — the Agent Workflow Graph: the nine-phase graph,
  gate modes, model routing, the compliance articles. Read this before starting
  or resuming any phase.
- `.workflow/state.json` — the live phase-machine state (current phase, gates
  approved so far). Read to see where the project actually stands right now.
- `docs/CONTEXT.md` — glossary, every ADR indexed and linked, the deployment
  statement. Start here to get oriented in the project as a whole.
- `docs/runbook.md` — incident detection and notification, phase 8 deliverable.
- `scripts/onboarding-wizard.sh` — run this on the real Mac to set up from
  scratch: prerequisites, `make setup`, the SQLCipher key, the Spotify
  Developer app (with the Development Mode gotcha that once broke every real
  sync), first run, observing, and both rollback paths.

## Project-specific rules

Mirrored from `specs/kickoff.md` section 12, which is the source; keep in sync.

1. Never import pyrekordbox outside `engine/src/companion/rb/`.
2. Never add a write operation to `master.db` outside `rb/writer.py`, and every
   write goes through `guard.check()` + `backup.create()` first. No exceptions,
   including tests (tests use a fixture copy of master.db).
3. Never commit real `master.db`, backups, tokens or `data/` contents.
4. API changes start in the OpenAPI schema; regenerate the client before
   touching frontend code.
5. Frontend colors/typography/spacing/radius only via the tokens in
   `web/design-input/theme.css`, never hardcoded values. Never bundle or
   reference SpotifyMixUI font files; the substitute stack (Inter + system-ui)
   ships under the original token names. DESIGN.md Do's and Don'ts are binding
   in review.
6. Code, comments, commits in English. UI copy in Dutch.
7. Each phase lands as its own PR with tests; golden matching fixtures may only
   be extended, never weakened.
