<!--
Sync Impact Report
Version change: (none) → 1.0.0
Rationale: Initial ratification. No prior constitution existed; this is the first
complete fill of the template for this project, so MAJOR (1.0.0) rather than a
0.x draft version.
Modified principles: n/a (initial set)
Added sections: Core Principles I-V, Engineering Baseline, Compliance Articles,
Governance
Removed sections: none
Deferred TODOs: none
Templates requiring follow-up: none — plan-template.md, spec-template.md,
tasks-template.md and checklist-template.md reference the constitution generically
and need no edits for this fill.
-->

# Rekordbox Companion Constitution

## Core Principles

### I. Local-First, Single-User
One process runs on the DJ's own machine, bound to `127.0.0.1` exclusively. There
is no cloud deployment, no multi-user access, and no remote exposure in v1. The
browser is UI only; all state and all writes live on the machine that runs
Rekordbox. Rationale: `master.db` can only be written safely from the machine
that holds it, so a local-only process removes an entire class of network and
auth risk instead of mitigating it.

### II. Guarded Writes to master.db
Every write to Rekordbox's `master.db` MUST go through `guard.check()` (refuse
while Rekordbox is running; verify the version pin 7.2.17) and then
`backup.create()` (timestamped backup) before the write happens, followed by a
readback verification. This applies with no exceptions, including tests, which
use a fixture copy of `master.db`. Only `engine/src/companion/rb/writer.py`
performs writes to `master.db`; only `engine/src/companion/rb/` imports
`pyrekordbox` at all. Rationale: `master.db` is the DJ's irreplaceable working
library; the guard/backup/readback sequence is the only defense against a
corrupting write, and confining the import surface to one directory makes that
defense auditable in one place.

### III. Read-Only Collection, No Metadata Edits
The app reads the Rekordbox collection (tracks, playlists, play counts) but MUST
NOT edit track metadata: no tags, no cues, no beat grids. Writes are limited to
playlists and folders (sync results, booking structure proposals). Rationale:
metadata editing is where Rekordbox itself is authoritative and where a subtle
write bug does the most damage to years of curation; the feature set does not
need it, so the risk is declined rather than contained.

### IV. Fuzzy Matching Is Primary, Not a Fallback
The local library is mp3/m4a without ISRC tags, so normalized artist+title fuzzy
scoring (rapidfuzz) is the primary match path; ISRC exact match is an
opportunistic fast lane only, with an expected near-zero hit rate on this
library. The golden test fixture set
(`engine/tests/fixtures/matching_golden.yaml`) may only be extended, never
weakened, and it gates any change to the matching pipeline. Rationale: treating
fuzzy matching as a fallback would under-invest in the review UI and the test
set that actually carry the product's accuracy; the golden set is the
non-negotiable proof that a pipeline change has not regressed real cases.

### V. Design Tokens Are Binding
Every rendered color, typography, spacing and radius value MUST trace to a token
in `web/design-input/theme.css`; no hardcoded design values. The SpotifyMixUI
font is proprietary and MUST NOT be bundled or referenced; the Inter + system-ui
substitute ships under the original token names. `DESIGN.md`'s Do's and Don'ts
are binding in review. Rationale: the token set is a delivered, fixed input, not
a starting point to riff on, and the font substitution is a legal boundary, not
a style preference.

## Engineering Baseline

- Test-driven development per task: tests are written and failing before
  implementation; red-green-refactor.
- Two-axis review per task: correctness (does it work, is it safe) and design
  (does it fit existing patterns, is it no more complex than needed).
- One atomic commit per task, in Conventional Commits format (`feat:`, `fix:`,
  `chore:`, `docs:`, `refactor:`).
- Each phase lands as its own pull request with tests.
- API changes start in the OpenAPI schema; the frontend client is regenerated
  from it before frontend code changes.

## Compliance Articles

Always active; `risk_class: minimal` (`specs/PROFILE.md`) sets the evidence bar
at one recorded line per article, including why it does or does not apply, per
`docs/process/workflow.md`. The articles themselves are never dropped.

**AVG/GDPR.** Privacy by design and by default. Data minimisation: a field that
is not needed is not collected. Every personal data element is recorded in a
PII inventory with its lawful basis, retention period and processors. A change
that adds personal data updates that inventory in the same commit.
Recorded line: this app processes one person's own Spotify OAuth token and
Rekordbox library data, held locally, never transmitted to a third party
beyond Spotify/Apple's own APIs the user already authorized; no PII inventory
is warranted at `minimal` risk class because no personal data of anyone other
than the single operator is collected or stored.

**NIS2.** Risk-based measures proportional to the system. Logging and
monitoring adequate to detect and reconstruct an incident, without logging the
personal data just minimised. Incident readiness: who is notified, in what
window, through which channel, written down before it is needed.
Recorded line: single-machine, `127.0.0.1`-only, no network exposure and no
shared infrastructure; incident readiness is "the operator notices and stops
the process," which is proportional at `minimal` risk class and needs no
separate incident plan.

**WCAG 2.2 AA.** Every user-facing story carries accessibility acceptance
criteria: keyboard operability, focus visibility, contrast, target size, form
errors that name the field and the fix. A story without them is not ready for
phase 5. Projects with no user interface record that fact rather than silently
skipping the article.
Recorded line: this project has a user interface (the React SPA), so this
article applies in full; every phase 2+ user story MUST carry its own
keyboard/focus/contrast/target-size/error-messaging acceptance criteria rather
than being waived here.

**OWASP.** Requirements are written ASVS-aligned. The Top 10 is a checklist in
both review and validation, not a slogan: authentication, access control,
injection, insecure design, misconfiguration, vulnerable dependencies,
integrity, logging, and server-side request forgery each get an explicit
verdict in phase 7.
Recorded line: no authentication surface exists beyond the Spotify OAuth PKCE
loopback flow and localhost binding; the phase 7 checklist still runs in full
against that reduced surface (injection via SQLite queries, dependency
hygiene, SSRF via the iTunes/Spotify HTTP clients) rather than being waived at
`minimal` risk class.

## Governance

This constitution supersedes ad-hoc practice for this project. Amendments
require a written reason and a version bump following semantic versioning:
MAJOR for a backward-incompatible principle removal or redefinition, MINOR for
a new principle or materially expanded guidance, PATCH for wording or
clarification only. Every amendment updates the Sync Impact Report at the top
of this file and the `Last Amended` date below.

All PRs and phase reviews MUST verify compliance with the Core Principles and
the Engineering Baseline above; a PR that violates one without a recorded,
reasoned exception in its description is not mergeable. Complexity beyond what
a task requires must be justified in the PR description, per the "no premature
abstraction" rule this project inherits from the global engineering
conventions. Use `CLAUDE.md` and `docs/process/workflow.md` for day-to-day
runtime development guidance; this document is the non-negotiable core they
both defer to.

**Version**: 1.0.0 | **Ratified**: 2026-08-16 | **Last Amended**: 2026-08-16
