# Phase 7 review and validation: Rekordbox Companion v1

**Feature**: `spec.md` | **Reviewed**: 2026-08-18 | **risk_class**: minimal |
**Branch**: `phase-6-implementation`, reviewed as the content of PR #165 into
`release`

Phase 6 delivered 109 tasks. This report is the phase 7 deliverable: a two-axis
review of the whole change set, the ten OWASP verdicts, the WCAG conformance
statement, the reconciled PII inventory, and validation against the scope note in
`specs/PROFILE.md`.

## Entry criteria

| Criterion | Status |
|---|---|
| Phase 6 complete | Yes, `.workflow/state.json` records phase 6 |
| Every task merged into `release` | **Deviation**: phase 6 landed on `phase-6-implementation` and is under review as PR #165 into `release`. Reviewing the branch rather than the merged `release` reviews the same content the release PR contains, which is what the phase file asks for; the merge was deliberately held until this report's blocking findings were closed, which they now are. |
| Test suite green | Yes. At review start: 429 pytest, 111 vitest, CI green on `c8de14a` including the Playwright suite. After this phase's fixes: 458 pytest, 156 vitest, `pnpm build` clean, lint and typecheck clean. |
| Spec, constraints, PII inventory, scope note available | Yes |
| Session runs the routed model | Yes, phase 7 is pinned to `claude-fable-5` and the review ran there |

Reviewer independence holds: every task was built by `claude-sonnet-5` (101) or
`claude-opus-4-8` (8), and reviewed by `claude-fable-5`. No task was reviewed by
its builder.

## Axis 1 and 2: correctness and design

The 109 tasks were reviewed in eight groups, each by an independent reviewer
reading the task text, the requirements it traces to, the implementation and its
tests. Both axes were applied per group: correctness asks whether the code does
what the spec says and whether the tests are real evidence rather than
tautologies; design asks whether the next change will be cheap.

| Group | Tasks | Verdict |
|---|---|---|
| Setup, foundational, polish | T001-T018, T101, T108, T109, T090-T095, T098 | Pass with 1 blocking, 7 advisory |
| US1 matching and sync backend | T019-T022, T097, T104, T105, T024-T030 | Pass with 1 blocking, 6 advisory |
| US1/US2 frontend | T023, T031-T037, T039-T041, T099, T100, T102 | Pass with 2 blocking, 3 advisory |
| US3 guarded write path | T042-T052, T096, T106 | Pass with 1 blocking, 5 advisory |
| US5 audio and collection | T038, T060-T065 | Pass with 1 blocking, 5 advisory |
| US4 missing tracks | T053-T059, T107 | Pass with 1 blocking, 3 advisory |
| US6 enrichment | T066-T077 | Pass with 2 blocking, 3 advisory |
| US7 bookings | T078-T088 | Pass with 3 blocking, 4 advisory |

What held up under scrutiny is worth recording as explicitly as what did not.
The guarded write path is genuinely sound: both callers run `guard.check()` then
`backup.create()` then the writer, a refusal or a backup failure is a 409 before
anything is written, a `write_log` row is written even when the writer raises,
add-only holds with no delete or reorder call outside tests, rotation keeps the
newest ten zipped per ADR 0016, and re-apply against the real fixture
`master.db` is integration-tested. `pyrekordbox` is imported only under
`engine/src/companion/rb/` in production code. The redacting log formatter is a
tested structural property, not a convention. The outbound-host allowlist is
enforced at transport level in both client factories. FR-030 is proven
byte-for-byte: an enrichment run leaves `master.db` unchanged.

### Blocking findings

Twelve findings were classified blocking. All twelve were fixed in this phase,
each with a test that fails against the pre-fix code; the status column names
the commit.

The twelfth is the one this review nearly shipped without. It was found only by
starting the app and looking at it, after the eight group reviews had finished,
because no reviewer had "is this story reachable in the running app" as its
remit: the US5 reviewer read the components and their tests, and the frontend
reviewer's scope was US1 and US2. Component-level review cannot catch an
unmounted feature, because the test mounts the component itself.

| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Bootstrap | Nothing ever runs `alembic upgrade head`: `make setup` only installs, `make run` and `scripts/dev.sh` start uvicorn directly, and `create_app()` applies no migrations. A fresh install on the DJ's Mac fails with "no such table" on the first database-touching request. | Fixed, `d43244a` |
| 2 | US1 matching | The remix/edit veto fired below the 75 bar as well, so a remix-marked Spotify track absent from the Collection came back `review` with meaningless candidates and could never become a Missing Track or enter the purchase flow. Resolved as a spec-reading question in ADR 0019: the veto only demotes. | Fixed, `2eb21ba` |
| 3 | US2 frontend | The entire US2 review UI was unwired: nothing in `web/src` imported `ReviewQueue`, `DualPlayback`, `QueueComplete` or `KeymapOverlay`, so the keyboard review flow and the on-screen key map were unreachable in the running app. | Fixed, `c468b67` |
| 4 | US2 frontend | `DualPlayback` fetched the Spotify player token once and cached it forever, ignoring `expires_in` (which is the remaining lifetime, as little as ~61s) and registering no `authentication_error` handler, so embedded playback died silently mid-review. | Fixed, `c468b67` |
| 5 | US3 write path | The duplicate-track contract test could not fail: the fake writer itself implemented the dedup it claimed to verify, and no test anywhere called `apply_playlist` with a duplicated list. A safety-area invariant was unpinned. | Fixed, `2487ee6` |
| 6 | US4 missing | `refresh-links` fired one unthrottled live iTunes request per open row with no per-row error handling, so a queue past the free-tier rate limit 500s mid-loop and rolls back even the links already fetched, against ADR 0011. | Fixed, `526393f` |
| 7 | US6 enrichment | The MusicBrainz 1 req/s limit was enforced only within a single `genres_for` call, not between tracks, giving ~1.8 req/s sustained: 503s and then an IP block on the multi-hour run this feature exists for. | Fixed, `f478b52` |
| 8 | US6 enrichment | Concurrent enrichment runs were unguarded. The start button's disabled state was local component state only, so a reload, a second tab, or a run started before page load all present an enabled button; two runs then race on the same SQLite file and can duplicate `enriched_genre` rows. | Fixed, `f478b52` |
| 9 | US7 bookings | Booking profiles could not be edited and a structure could not be linked to one anywhere in the UI, so the seeded profiles stayed empty and suggestions always ran unfiltered: FR-031's "editable" and US7 scenarios 1 and 3 were dead ends despite a working backend. | Fixed, `fe95fa7` |
| 10 | US7 bookings | The suggestions fetch passed no `limit`, so selecting a node fetched the whole collection and rendered a list item with two buttons per track: a multi-MB response and tens of thousands of DOM nodes per click at the target scale. | Fixed, `fe95fa7` |
| 11 | US7 bookings | The suggestions query bound one SQL parameter per collection entry, roughly 20k per request and a hard `too many SQL variables` failure above SQLite's 32,766 cap, inside the project's own 40k sizing envelope. | Fixed, `fe95fa7` |
| 12 | US5 frontend | `TrackTable` and `PlayerBar` were never imported by anything, so the collection browser and the player were unreachable in the running app, exactly like US2's components. `App.tsx` recorded the gap in a comment ("not wired in here yet, a pre-existing gap") rather than as a finding, and no test covered the page as a whole. | Fixed |

### Advisory findings

Recorded rather than fixed where they do not change behaviour the owner can
reach, fixed where the fix was cheap and local. All are listed so none is
absorbed silently.

Correctness, fixed in this phase: unvalidated `limit`/`offset` on
`GET /api/collection` (a negative limit produced an unhandled 500); a leaked
SQLCipher connection per request from a plain-return `get_database` dependency;
`parent_id` not mapping pyrekordbox's literal `"root"` to `None`, which would
break playlist hierarchy reconstruction on the real database; a
mutate-while-iterating race in the SSE `publish()` fan-out; an invalid
`bytes=5-3` Range answered 416 where RFC 7233 requires it be ignored; a
non-finite duration on the transcode path leaving the seek slider enabled with
`max="Infinity"` and a misleading `aria-valuetext`; a diagnostic refetch in
`PlayerBar` that started a second unread ffmpeg transcode; load errors rendering
as "no results" in `TrackTable` and swallowed errors in `MissingQueue`; a
candidate-index carryover in `ReviewQueue` that could accept the wrong candidate
on a rapid keypress; `SpotifyConnection` crashing the page when the status fetch
fails; `update_profile` returning a 500 instead of 422 on a duplicate name and
never regenerating its slug; `update_node` accepting a cross-structure or
cyclic parent, caught only later by a 500 after a backup had been made; a
position derived from a sibling count rather than the maximum; the `created`
flag never surfaced, so a recreated Target Playlist read as an ordinary update
against FR-019; `coverage_pct` measuring `enrichment_state` rows rather than the
collection, which is the number the owner will judge SC-008 by; the enrichment
panel never resetting after a circuit-breaker stop.

Correctness, found while verifying the fixes rather than in the group reviews:
two tests in `engine/tests/test_main.py` registered a synthetic route after
`create_app()`, which the SPA catch-all mount swallows whenever `web/dist`
exists. They therefore passed only on a machine that had never built the
frontend, which is exactly why CI stayed green (its backend job never builds
`web/`) and why they went red the moment the frontend was built locally. Fixed
by inserting the route ahead of the mount, in a shared helper that says why.

Design and hygiene, fixed: `Tree.tsx` hardcoding a 16px indent step instead of a
spacing token, the one live violation of project rule 5; the golden-set
append-only guard comparing ids only, so an in-place edit of a case was
invisible; the `openapi` script emitting output that fails `format:check`; a
test that mutated the repository's real `.env`; three docstrings documenting the
inverse of the decision beside them (a sync handler described as async, a
fractional duration penalty described as per-whole-second, an SSE event type
described as not yet built); `plan.md` still counting five architecture seams
where `architecture.md` documents six.

One accessibility weakness surfaced while wiring the page together and is
recorded rather than fixed: every section title ("Ontbrekende nummers",
"Genre-verrijking", "Boekingstructuren" and the rest) is a styled paragraph
rather than a real heading, so the page offers a screen reader no heading
structure to navigate by. axe does not flag it and no phase 2 criterion names it
explicitly, which is why it survived the sweep, but it undercuts the same
keyboard-and-screen-reader story those criteria are about. Carried as backlog
item B9.

Design, recorded and not fixed, with the reason. Each is carried in
`backlog-post-v1.md` rather than in `tasks.md`, because the phase machine refuses
to complete phases 6 and 7 while any task line there lacks a recorded builder:

- The guard-then-backup-then-write-then-log orchestration is duplicated by hand
  in both calling endpoints, and nothing mechanical stops a third endpoint from
  calling `writer.apply_*` directly. The invariant is currently remembered, not
  unforgettable. A shared orchestrator plus a conformance test that fails on any
  `pyrekordbox` import outside `rb/` and any writer call outside it would make
  it structural. Deferred as a refactor of correct code, tracked as backlog item B1.
- `backup.create()` zips `master.db` and `masterPlaylists6.xml` but not the
  SQLite `-wal`/`-shm` sidecars. If Rekordbox ever runs `master.db` in WAL mode
  and exits uncleanly, a backup verifies readable yet misses the newest
  transactions. Needs checking on the Mac against the real install, tracked as
  backlog item B2.
- Two test files import `pyrekordbox` directly to verify the writer with
  something other than the writer. That is sound test design but it is outside
  ADR 0017's stated exception, so the rule's wording and the practice disagree.
  Tracked as backlog item B3.
- The enrichment panel receives per-chunk SSE progress but uses it only as a
  completion probe, so a multi-hour run shows a frozen status line. SSE was
  chosen precisely to stream progress. Tracked as backlog item B4.

## OWASP Top 10 verdicts

`risk_class` is `minimal`, so `constraints.md` recorded one ASVS-aligned line per
area. The phase 7 exit criteria nonetheless require an explicit verdict per Top
10 item, with evidence. The attack surface is a single-user app bound to
`127.0.0.1` on the operator's own machine, whose only credential flow is Spotify
OAuth PKCE.

| # | Item | Verdict | Evidence |
|---|---|---|---|
| A01 | Broken access control | Not applicable, with reason | One operator, one role, no multi-tenant data. The loopback binding is the access control: `Makefile` defaults uvicorn to `127.0.0.1` and only the dev container overrides it to reach across the Docker namespace. An earlier IDOR-shaped defect in the lookup endpoints was found and fixed during phase 6. |
| A02 | Cryptographic failures | Pass | No cryptography is implemented in this app. Tokens are stored in a local owner-only database file, the SQLCipher key is read from the environment and never persisted or logged, and all outbound calls are HTTPS to the allowlisted hosts. |
| A03 | Injection | Pass | Database access is SQLAlchemy 2.x throughout with parameter binding, no string-built SQL exists in the tree. Playlist input is parsed to a Spotify playlist id before use, never interpolated. The ffmpeg fallback invokes an argument list, never a shell. |
| A04 | Insecure design | Pass, with one deferred hardening | The write path is designed around refusal: guard, then verified backup, then add-only write, then readback and an audit row, with a 409 before anything is touched. The deferred item is that the sequence is enforced by convention in two call sites rather than by a shared orchestrator plus a conformance test (backlog item B1). |
| A05 | Security misconfiguration | Pass | Loopback binding by default; no CORS middleware is installed, so no permissive origin policy exists; `.env` is git-ignored with `env.example` kept current; a startup check flags a group- or world-readable `.env`, tested in `engine/tests/security/test_asvs_boundaries.py`. |
| A06 | Vulnerable and outdated components | Pass | Pinned dependencies with committed lockfiles on both sides (`engine/uv.lock`, `web/pnpm-lock.yaml`), `pyrekordbox` pinned compatible with Rekordbox 7.2.17 per ADR 0002, and `.github/dependabot.yml` watching github-actions, npm and uv. No automated CVE scan runs in CI; for a localhost single-user proof-of-value at `risk_class: minimal`, dependabot is the proportional measure. |
| A07 | Identification and authentication failures | Not applicable, with reason | No app-level login exists. The Spotify flow is OAuth PKCE with a loopback redirect, a `state` parameter, and no client secret in the repository. Disconnect deletes the stored session outright. |
| A08 | Software and data integrity failures | Pass | Every Rekordbox write is preceded by a verified backup and followed by readback verification, with a `write_log` row written even on failure; add-only means a failed or partial write cannot destroy manual curation. Lockfiles cover dependency integrity. |
| A09 | Security logging and monitoring failures | Pass, with one deviation | Guard refusals, backup creation and rotation, writes with their readback verdict, and run summaries are all logged as structured JSON, with credential redaction enforced in the formatter rather than at call sites. Deviation: `constraints.md` says logs are local files rotated by size, while `configure_logging()` installs a `StreamHandler`, so logs go to the terminal that runs the app and are not rotated files. For a single operator watching the terminal this still satisfies the NIS2 line below, but the plan and the implementation disagree; tracked as backlog item B5. |
| A10 | Server-side request forgery | Pass | Outbound HTTP is confined to a documented host allowlist enforced at transport level in both client factories, and refused before any network IO for a disallowed host, including hosts crafted to look allowed. No user-supplied URL is ever fetched: a playlist URL is parsed to an id, and store links are built from a fixed host. Covered by `engine/tests/security/test_asvs_boundaries.py`. |

## WCAG 2.2 AA conformance statement

Every user-facing story carries accessibility acceptance criteria from phase 2.
The automated evidence is an axe-core sweep in `web/tests/e2e/accessibility.spec.ts`,
running in CI, and the component suites assert keyboard operability, focus
visibility, text-not-colour status conveyance and 24x24 minimum targets.

Conformance is claimed for the delivered SPA at AA, with these recorded
deviations:

| Deviation | Owner | Date |
|---|---|---|
| The axe sweep covers the default page state and the match-report and apply flow, not the review-queue or booking-tree editing states, which are the densest interactive UI. Blocking finding 3 was the reason the review states were unreachable at all; now that they are wired, the sweep should be extended to them. Tracked as backlog item B6. | Martien | 2026-09-01 |
| The manual half of the accessibility pass, a keyboard-only walkthrough and physical measurement of 24x24 targets, is specified but has no recorded execution. It needs the owner at the keyboard and cannot be delegated to CI. Tracked as backlog item B7. | Martien | 2026-09-01 |
| In the review queue the active candidate was distinguished by colour and shade alone. Assistive technology was served correctly by `aria-selected`/`aria-activedescendant`, but the sighted focus position needed a non-colour cue (WCAG 1.4.1). Fixed in this phase; retest belongs to the extended sweep above. | Martien | 2026-09-01 |

## AVG/GDPR: reconciled PII inventory

Reconciled in both directions against what the code actually stores and logs.

Inventory to code: element 1 (OAuth access and refresh tokens) and element 2
(account identity: account id, display name, Premium product) both live in the
single-row `spotify_auth` table in the local database, exactly as recorded.
`disconnect` deletes that row outright rather than flagging it inactive, so the
recorded deletion path is real. Element 3 (Rekordbox library data and its
backups) lives where the inventory says it does, on the operator's machine, and
backups rotate at ten zipped per ADR 0016.

Code to inventory: every table in `db/models.py` was walked. `playlist_link`,
`sync_session`, `sync_track`, `missing_track`, `write_log`, `app_config`,
`enriched_genre`, `enrichment_state`, `booking_profile`,
`booking_profile_genre_tag`, `structure`, `structure_node`, `structure_track`
and `suggestion_dismissal` hold track metadata, Rekordbox content ids, match
scores, playlist structure and audit rows: the operator's own working data, no
third-party personal data, all covered by element 3. No field exists in the
database that the inventory does not account for.

One addition the reconciliation surfaced: the disconnect log line records
`account_id`, so an element-2 identifier reaches the log file. It is the
operator's own identifier, on the operator's own machine, in a line whose whole
purpose is to record that the session was deleted, and it dies with normal log
rotation. Recorded here rather than left implicit; no inventory change is
needed because the element and its basis are already listed, but the inventory's
"Where it lives" for element 2 now also means the local log.

Nothing is transmitted anywhere except to Spotify itself, which the operator
already contracted with. No analytics or telemetry of any kind exists in the
tree.

## NIS2: logging, monitoring, incident readiness

The phase 3 plan is implemented, with the one deviation recorded under A09: the
logged set matches the plan line for line, and the deliberately-never-logged set
is enforced structurally by the redacting formatter rather than by asking every
call site to remember. An incident could be reconstructed from what is logged:
for the one scenario that matters, a bad Rekordbox write, the log carries the
guard verdict, the backup path and timestamp, the write with its readback
verdict, and there is a `write_log` row in the database even when the write
raised. Detection is the operator noticing malfunction, notification is
self-directed and immediate, and the channel is the app's UI and the terminal it
runs in, which is proportional for a single-user localhost app.

## Validation against the scope note

The scope note in `specs/PROFILE.md` is met on all four in-scope items: Spotify
playlists are matched against the local Rekordbox collection; matches are
written back as Rekordbox playlists, guarded, with a verified backup before
every write; missing tracks link to the Apple Music / iTunes Store on the NL
storefront; and booking-type playlist structures are generated from playlist
membership and per-track play counts.

The four explicit exclusions hold. No cloud or multi-user deployment exists: the
app binds to loopback, `deploy_target` is `none`, and the central Postgres
database stays unused and reserved for the P2 analytics mirror. Nothing
downloads or rips audio: the store integration produces links only, and the
audio path streams local files the operator already owns. No Rekordbox track
metadata is edited: enrichment is app-side and there is a byte-for-byte test
proving a run leaves `master.db` untouched, and the only write is add-only
playlist creation. No native app packaging exists.

Drift from the scope note: none. Two items of scope were cut inside the
delivered feature set rather than drifting outside it, and both are recorded
where the work is tracked: the Spotify genre source was dropped in favour of
MusicBrainz (ADR 0018), and the deliverable is a `proof-of-value`, so the
Golden Set holds four illustrative stub cases rather than the 50 real cases
SC-003 requires. That last one is a genuine open gate, not a deviation absorbed
silently, and it is why T094 stays unchecked.

## What the development fixture can and cannot show

The app was run end to end in the development container against the
owner-supplied fixture `master.db`, served through `scripts/dev-serve-with-db.py`
(dev-only: it builds the fake Pioneer tree pyrekordbox's detection expects
around a copy of a database you name, because this container has no Rekordbox
install). `/api/health` reports `status: ok`, `version_pin_ok: true` and
`ffmpeg_ok: true`, the SPA is served, a reindex reads 119 tracks in 246ms, and
the collection and playlist endpoints answer with no console errors in the
browser.

What the fixture supports: 119 tracks, 87 of them with an artist, 34 with a BPM,
in mp3 and wav, including remix-marked titles, which is real enough to exercise
matching, the collection browser, playback and the guarded write path.

What it cannot show, which bounds what any demo here proves: every play count in
the fixture is zero, so US7's suggestion ranking has nothing to rank on and
SC-009 cannot be judged; only 34 tracks carry a BPM, so profile BPM filtering is
thin; and the Golden Set is still four stubs, so SC-002 and SC-003 stay
unproven. All three need the owner's real library, which is what T089 and T094
are for.

## Open items the owner must close

These cannot be closed by review; they need the owner, the real Mac, or the real
Rekordbox install. Each is tracked in `tasks.md` and left unchecked there.

- **T089**: the quickstart validation scenarios end to end, on the Mac, against
  the real `master.db` and a real Spotify account.
- **T094**: SC-003's Golden Set. The fixture currently holds four stub cases,
  not 50 real ones with 10 hard cases, so SC-002 and SC-003 are unproven and
  the matching thresholds are unvalidated against real data.
- **T103**: the SC-009 booking-prep judgement, on the first real booking
  prepared with the app.
- The two WCAG deviations above, plus the extended axe sweep.
- **B2**: whether Rekordbox runs `master.db` in WAL mode, which decides
  whether backups must include the SQLite sidecars.

## Exit criteria

| Criterion | Status |
|---|---|
| Every OWASP Top 10 item has an explicit verdict | Yes, ten verdicts above with evidence |
| WCAG 2.2 AA met, or each deviation has an owner and a date | Yes, three deviations recorded with owner and date |
| PII inventory matches what the code stores and logs, both directions | Yes, reconciled above |
| Result matches the scope note, drift written down | Yes, no drift; two in-scope cuts recorded |
| `routing.py check 7` passes, every task reviewed by a non-builder | Yes |
