# Constraints

Phase 3 deliverable. Sources: owner grilling on 2026-08-16 (non-functionals),
`specs/001-companion-v1/spec.md` (behavioural numbers), `specs/PROFILE.md`
(`risk_class: minimal`, which scales the NIS2/OWASP/AVG sections to recorded
lines with reasons). Every entry is a number, a verdict, or an explicit
"unbounded, accepted". Constraints that eliminate design options carry an ADR
reference so phase 4 cites instead of rediscovers.

## Load and concurrency

- Users: exactly 1 (the owner), on 1 machine, no concurrent use. Source: owner.
- Sync input bound: playlists up to 1.000 tracks are supported; the 30-second
  match-report promise (SC-001) is measured at 100 tracks. Source: owner.
- Background work (matching, enrichment) never blocks read-only features
  (FR-040); no other concurrency requirement exists.

## Data volume

- Collection: 20.000+ tracks today and growing. All collection-facing features
  are dimensioned for 20.000 and tested at 30.000. Source: owner grilling;
  spec updated (US5, FR-024, SC-005) from its earlier 10.000 assumption.
- Rekordbox database: order of hundreds of MB; every backup is a full copy.
- Companion-owned data (sessions, matches, enrichment, structures): small by
  construction, no bound needed; it references Rekordbox ids instead of
  duplicating track data.

## Latency

- Match report: complete within 30 seconds for a 100-track playlist (SC-001).
- Collection search: results within 100 milliseconds per keystroke at 20.000+
  tracks (SC-005).
- Playback start and apply duration: not bounded, accepted; a write's duration
  is dominated by the backup copy and correctness beats speed there. Source:
  owner (defaults accepted).

## Availability and operations

- Availability: best effort. Recovery plan is restarting the process; there is
  no uptime target, no monitoring service, no on-call. Verdict: accepted.
- Operational ownership: the owner runs, updates and recovers the app himself.
- Team: 1 owner plus AI agents under the workflow graph.

## Retention and deletion

- Rekordbox database backups: keep all, the app never deletes a backup; disk
  usage is unbounded and accepted; cleanup is a manual act by the owner
  (ADR 0010). Source: owner grilling.
- Spotify OAuth tokens and account identity: kept until the owner disconnects
  the account in the app or revokes at Spotify; the disconnect action deletes
  them locally. Deletion path: UI action. See
  `specs/001-companion-v1/pii-inventory.md`.
- Companion-owned data (sync history, enrichment, structures): kept
  indefinitely on the owner's machine; not personal data of any third party;
  deletable by deleting the app's data directory. Verdict: unbounded, accepted.

## Budget and deadline

- Budget: owner's own time plus free API tiers only. Spotify app in developer
  mode, iTunes Search API, and any enrichment source must be usable without
  payment; paid services are closed off (ADR 0011). Source: owner grilling.
- Deadline: none. Quality over speed; the proof-of-value is done when it meets
  its success criteria. Source: owner grilling.

## NIS2 — logging, monitoring, incident readiness (risk_class: minimal)

Recorded line: single machine, `127.0.0.1`-only, one operator; incident
detection is the operator noticing malfunction, notification is self-directed
and immediate, the channel is the app's UI and the terminal it runs in; no
separate incident plan is proportional here.

Logging plan, binding for implementation:

- Logged: every guard refusal with its reason; every backup creation with
  timestamp and path; every Rekordbox write with its readback verdict; sync
  session and enrichment run summaries (counts, duration); errors with stack
  traces.
- Deliberately not logged: OAuth tokens or any credential, the SQLCipher key,
  request headers, audio content, and full library dumps. Log lines reference
  Rekordbox content ids, not file paths, wherever an id suffices.
- Logs are local files, rotated by size, and are themselves covered by the
  "keep all, manual cleanup" retention verdict above.

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
2. Enrichment coverage on a 20.000+ track mp3/m4a library — spike decides the
   source(s), within the free-tier constraint (ADR 0011).
3. Spotify Web Playback SDK on `127.0.0.1` — spike decides whether embedded
   full-track playback holds; fallback is local preview plus opening the track
   in Spotify's own client.
