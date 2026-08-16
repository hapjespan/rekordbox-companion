# Constraints

Phase 3 deliverable. Sources: owner grilling on 2026-08-16 (non-functionals,
two rounds — see `docs/grilling/2026-08-16-phase-3.md` for the second round and
the reconciliation of the two), `specs/001-companion-v1/spec.md` (behavioural
numbers), `specs/PROFILE.md` (`risk_class: minimal`, which scales the
NIS2/OWASP/AVG sections to recorded lines with reasons). Every entry is a
number, a verdict, or an explicit "unbounded, accepted". Constraints that
eliminate design options carry an ADR reference so phase 4 cites instead of
rediscovers.

## Load and concurrency

- Users: exactly 1 (the owner), on 1 machine, no concurrent use. Source: owner.
- Sync input bound: playlists up to 999 tracks; a larger playlist is refused
  before the Sync Session starts, with a message naming the limit. The
  30-second match-report promise (SC-001) is measured at 100 tracks; at the
  999 cap the full report completes within 5 minutes. Source: owner (D12).
- Background work (matching, enrichment) never blocks read-only features
  (FR-040); at most 1 Sync Session and 1 enrichment run execute at a time.

## Data volume

- Collection: 30.000+ tracks today and growing. All collection-facing features
  are dimensioned for 30.000+ and performance-tested at 40.000. Source: owner
  grilling (D11, confirmed in reconciliation); spec updated (US5, FR-024,
  SC-005) from its earlier 10.000 assumption.
- Rekordbox database: order of hundreds of MB; every backup is a full copy,
  zip-compressed on creation (ADR 0016).
- Companion-owned data (sessions, matches, enrichment, structures): small by
  construction, no bound needed; it references Rekordbox ids instead of
  duplicating track data.

## Latency

- Match report: complete within 30 seconds for a 100-track playlist (SC-001);
  within 5 minutes at the 999-track cap (D12).
- Collection search: results within 100 milliseconds per keystroke at 30.000+
  tracks, tested at 40.000 (SC-005).
- Enrichment: a full run over the Collection completes within 12 hours and is
  resumable after interruption; an incremental run over new tracks completes
  within 30 minutes (grilling Q4, ADR 0013).
- Playback start and apply duration: not bounded, accepted; a write's duration
  is dominated by the backup copy and correctness beats speed there. Source:
  owner (defaults accepted).

## Availability and operations

- Availability: best effort. Recovery plan is restarting the process; there is
  no uptime target, no monitoring service, no on-call. Verdict: accepted.
- Operational ownership: the owner runs, updates and recovers the app himself.
- Team: 1 owner plus AI agents under the workflow graph.

## Target machine

- Apple Silicon M3, 16 GB RAM, macOS, Rekordbox 7.2.17 pinned (ADR 0002).
  Free disk: sufficient, unbounded, accepted — guarded per write by the disk
  headroom check (2x `master.db` size, phase 4 grilling). Source: owner (D16).
- Transcoding: on-the-fly through ffmpeg, no persistent cache in v1 (D17).
  The library is mp3/m4a, so the fallback is a rare path.
- Development runs in the Linux container against a fixture `master.db`;
  anything requiring the real install is verified on the Mac.

## Retention and deletion

- Rekordbox database backups: zip-compressed, the newest 10 are kept; pruning
  runs only after a new backup has been created and verified readable, never
  as a standalone background job (ADR 0016, which supersedes ADR 0010's
  keep-all policy after owner reconciliation). A backup that fails
  verification blocks the write, the same as insufficient disk space.
- Spotify OAuth tokens and account identity: kept until the owner disconnects
  the account in the app or revokes at Spotify; the disconnect action deletes
  them locally. Deletion path: UI action. See
  `specs/001-companion-v1/pii-inventory.md`.
- Companion-owned data (sync history, enrichment, structures): kept
  indefinitely on the owner's machine; not personal data of any third party;
  deletable by deleting the app's data directory. Verdict: unbounded,
  accepted (D17). History is a feature: the ignored status must persist, so
  v1 ships no cleanup.

## Budget and deadline

- Budget: owner's own time plus free API tiers only. Spotify app in developer
  mode, iTunes Search API, and any enrichment source must be usable without
  payment; paid services are closed off (ADR 0011). Source: owner grilling.
- Deadline: none. Quality over speed; the proof-of-value is done when it meets
  its success criteria. Source: owner grilling (D15).

## NIS2 — logging, monitoring, incident readiness (risk_class: minimal)

Recorded line: single machine, `127.0.0.1`-only, one operator; incident
detection is the operator noticing malfunction, notification is self-directed
and immediate, the channel is the app's UI and the terminal it runs in; no
separate incident plan is proportional here.

Logging plan, binding for implementation:

- Logged: every guard refusal with its reason; every backup creation and every
  backup pruned by rotation, with timestamp and path; every Rekordbox write
  with its readback verdict; sync session and enrichment run summaries
  (counts, duration); errors with stack traces.
- Deliberately not logged: OAuth tokens or any credential, the SQLCipher key,
  request headers, audio content, and full library dumps. Log lines reference
  Rekordbox content ids, not file paths, wherever an id suffices.
- Logs are local files, rotated by size; log retention follows the rotation,
  cleanup beyond that is a manual act by the owner.

## OWASP — security requirements (ASVS-aligned, risk_class: minimal)

Recorded line: the attack surface is a localhost-bound single-user app whose
only auth flow is Spotify OAuth PKCE; the full OWASP checklist still runs in
phase 7 against that reduced surface. Requirements, each traced to its ASVS
area:

- ASVS V2 (authentication): no app-level login exists; out of scope with
  reason: the app binds to `127.0.0.1` and serves one operator on their own
  machine. The Spotify flow uses OAuth PKCE with a loopback redirect and no
  client secret in the repository.
- ASVS V3 (session management): Spotify tokens live in the local app database
  with owner-only file permissions, are never written to logs, and die with
  the disconnect action.
- ASVS V4 (access control): out of scope with reason: one user, one role; the
  localhost binding is the access control.
- ASVS V5 (validation, sanitisation, encoding): every external payload
  (Spotify API, iTunes Search, enrichment source) is schema-validated at the
  boundary; database access is parameterised throughout; playlist input is
  parsed to a playlist id, and raw user-supplied URLs are never fetched.
- ASVS V6/V12 (secrets, files): no secrets in git (`.env` stays out,
  `env.example` current); the SQLCipher key and tokens are never committed or
  logged; streamed file paths always resolve from Rekordbox content ids, never
  from client-supplied paths.
- ASVS V10/V14 (dependencies, configuration): boring, pinned dependencies with
  lockfiles; pyrekordbox is pinned compatible with Rekordbox 7.2.17 (ADR 0002);
  outbound HTTP is restricted to the fixed set of API hosts (Spotify, Apple,
  the chosen enrichment source), which also answers SSRF.

## AVG/GDPR (risk_class: minimal)

Recorded line: the only personal data is the operator's own Spotify
authorisation and account identity, held locally, transmitted to no one beyond
Spotify itself; the PII inventory
(`specs/001-companion-v1/pii-inventory.md`) records basis, retention and
processors for each element, and the retention/deletion requirements above
carry it forward. Processor: Spotify, already contracted by the owner. A
change that adds a personal data element updates the inventory in the same
commit (constitution).

## Open unknowns carried into phase 4

These are constraints on the architecture phase, not surprises for
implementation (phase 1 grilling, "three biggest unknowns"):

1. pyrekordbox write compatibility with Rekordbox 7.2.17 — smoke test against
   the fixture database before the write path is designed final.
2. Enrichment coverage on a 30.000+ track mp3/m4a library — spike decides the
   source(s), within the free-tier constraint (ADR 0011).
3. Spotify Web Playback SDK on `127.0.0.1` — spike decides whether embedded
   full-track playback holds; fallback is local preview plus opening the track
   in Spotify's own client.
