# Constraints — Rekordbox Companion v1

Phase 3 deliverable. Every entry is a number or an explicit verdict
("unbounded, accepted"); adjectives do not count as constraints. Sources: the
phase 3 grilling record (`docs/grilling/2026-08-16-phase-3.md`, D11–D17), the
spec (`specs/001-companion-v1/spec.md`) and `specs/PROFILE.md`
(`risk_class: minimal`). Phase 4 cites these entries by id instead of
rediscovering them.

## Load and concurrency

- **C-01** Operators: exactly 1, the owner-DJ. No multi-user path exists
  (spec FR-037).
- **C-02** Network exposure: the app binds to 127.0.0.1:8787 only; nothing
  listens on any other interface.
- **C-03** Concurrent background work: at most 1 Sync Session and 1 enrichment
  run at a time; read-only features stay usable meanwhile (spec FR-040).
- **C-04** Playlist size: 999 tracks maximum per Spotify playlist. A larger
  playlist is refused before the Sync Session starts, with a message naming
  the limit (D12).

## Data volume

- **C-05** Collection: 30.000+ tracks today. Every performance criterion is
  verified at 30.000 tracks; the spec's "10.000+" figures are a floor,
  superseded upward (D11). No design may carry a hard limit below 30.000 or
  scale worse than near-linearly in collection size.
- **C-06** Companion-owned data (sessions, matches, missing queue, enriched
  genres, structures): unbounded, accepted (D17). It is text-scale metadata;
  history is a feature (ignored status must persist), so v1 ships no cleanup.

## Latency

- **C-07** Collection search: results within 100 ms per keystroke at 30.000
  tracks (spec SC-005 at the C-05 scale).
- **C-08** Match report: 100-track playlist complete within 30 seconds (spec
  SC-001); 999-track playlist (the C-04 cap) complete within 5 minutes (D12).
- **C-09** Enrichment: full run over the Collection within 12 hours and
  resumable after interruption; incremental run over new tracks within 30
  minutes (D14 grilling Q4).
- **C-10** Apply (guard, backup, write, readback): no numeric bound set;
  unbounded, accepted. The flow shows progress and the backup step dominates;
  on the target machine it is expected to be seconds, not minutes.

## Retention and backups

- **C-11** Rekordbox database Backups: one per write (spec FR-016),
  zip-compressed, the newest 10 kept. Pruning runs only after a new backup has
  been created and verified readable, never as a standalone background job
  (D13).
- **C-12** Backup integrity: a Backup counts as created only when the zip
  archive verifies as readable; an unverifiable backup blocks the write, the
  same as insufficient disk space (spec edge case).
- **C-13** Spotify tokens and account identity: retained until the operator
  disconnects, then deleted (PII inventory rows 1–2).

## Availability and recovery

- **C-14** Uptime: no requirement; unbounded, accepted. Restarting the process
  is the recovery mechanism (D17).
- **C-15** The companion's own database rides the machine backup (Time
  Machine); the app ships no own-data backup feature (D17).
- **C-16** Degraded start: a missing `master.db` at the expected path yields a
  named degraded state blocking Rekordbox-backed features, not per-screen
  errors (spec edge case).

## Budget

- **C-17** Recurring cost: €0 beyond the owner's existing Spotify Premium.
  External sources (enrichment, store-link lookup) use free API tiers only
  (D14, ADR 0010).

## Deadline

- **C-18** None; unbounded, accepted. The owner paces the project (D15). The
  first real booking prepared with the app is the SC-009 measurement, not a
  date.

## Team and operational ownership

- **C-19** Team: one human (owner) plus the agent workflow. Operational owner:
  the owner-DJ, on his own Mac (D17).

## Target machine

- **C-20** Apple Silicon M3, 16 GB RAM, macOS, Rekordbox 7.2.17 pinned (ADR
  0002). Free disk: unbounded, accepted, guarded per write by the pre-backup
  disk check (D16). Development runs in the Linux container against a fixture
  `master.db`; anything requiring the real install is verified on the Mac.
- **C-21** Transcoding: on-the-fly through ffmpeg, no persistent cache in v1
  (D17). The library is mp3/m4a, so the fallback is a rare path.

## Compliance (risk_class: minimal — one recorded line per article)

- **NIS2**: Logged, locally and rotating: guard decisions, backup creation and
  pruning, applies with track counts, errors. Deliberately not logged: OAuth
  tokens or any credential, request bodies. Incident detection is the single
  operator noticing misbehaviour; the response, written down here before it is
  needed: stop the process, restore the newest Backup (the Apply flow names
  it), no one else to notify because no one else is affected.
- **AVG/GDPR**: No new personal data enters in this phase; the PII inventory
  carries forward unchanged except that Backup retention becomes automatic
  rotation (newest 10, C-11) instead of manual deletion — updated in the
  inventory in the same commit. Deletion paths: tokens and identity on
  disconnect (C-13), backups by rotation (C-11).
- **WCAG 2.2 AA**: No constraint in this phase touches the UI; the per-story
  accessibility criteria from phase 2 stand unreduced.
- **OWASP**: Security requirements below, ASVS-aligned at the level this
  system warrants.

## Security requirements (ASVS-aligned)

- **SEC-01** (V1/V4, access control): out of scope with reason — a single
  operator on localhost; no accounts, roles or authorisation model exist to
  secure (C-01, C-02).
- **SEC-02** (V2/V3, authentication and sessions): the only authentication is
  Spotify OAuth with PKCE; tokens are stored only in the companion's local
  database and never logged or committed. No own session or password handling
  exists.
- **SEC-03** (V5, input handling): every Spotify playlist URL is validated
  before use; audio streaming resolves files only through Rekordbox content
  ids, never through client-supplied filesystem paths, closing path traversal.
- **SEC-04** (V10/SSRF): outbound requests go exclusively to the fixed API
  hosts of Spotify, the iTunes Search API and the chosen enrichment source;
  no user-supplied host is ever fetched.
- **SEC-05** (V6/V8, secrets and data): `.env` and the local database stay out
  of git (project rule 3); backups of `master.db` are treated as the library
  itself and never leave the machine.
- **SEC-06** (V14, dependencies): dependencies are pinned through uv and pnpm
  lockfiles; the guarded write path (guard, backup, readback) is the integrity
  control for the one irreplaceable asset.
