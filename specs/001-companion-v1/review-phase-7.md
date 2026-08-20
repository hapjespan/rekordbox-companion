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
| Test suite green | Yes, locally. At review start: 429 pytest, 111 vitest, CI green on `c8de14a`. After the first revision: 458 pytest, 175 vitest. After the second: 534 pytest, 346 vitest, 7 Playwright with three axe sweeps, `pnpm build`, `tsc --noEmit`, ESLint and Prettier clean. CI itself stopped running mid-phase and is not evidence; the second revision explains why and what replaced it. |
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

Thirteen findings were classified blocking. All thirteen were fixed in this phase,
each with a test that fails against the pre-fix code; the status column names
the commit.

The twelfth and thirteenth are the ones this review nearly shipped without. Both
were found only by starting the app and using it, after the eight group reviews had finished,
because no reviewer had "is this story reachable in the running app" as its
remit: the US5 reviewer read the components and their tests, and the frontend
reviewer's scope was US1 and US2. Component-level review cannot catch an
unmounted feature or a missing step between features, because each test supplies
its own component and its own data.

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
| 13 | US5 / collection index | The collection index is an in-memory cache rebuilt from `master.db` on demand (ADR 0012), and nothing ever demanded it: no UI control called `POST /api/collection/reindex` and no startup path filled it. Every freshly started app therefore showed an empty collection, empty enrichment coverage and empty suggestions, with no way to fix it from the UI. Verified by restarting the app: the collection reported `total: 0` until an external POST. | Fixed |

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

These ten verdicts were reached before the second revision added four endpoints and
an `ids` filter, so they were held against that new surface rather than assumed to
carry over. All five additions are read-only and none of them widens the attack
surface the verdicts describe. A01 is unchanged: still one operator, one role, and
loopback as the access control; none of the new endpoints takes an identifier that
selects between users, and the collection ids they accept address the operator's
own library. A03 is unchanged: the `ids` filter binds parameters through SQLAlchemy
like everything else and is capped, so it cannot become an unbounded IN clause,
which is the shape a phase 7 finding already caught once on this endpoint. A10 is
unchanged: the Spotify playlists endpoint calls a fixed allowlisted host through
the existing client and follows only Spotify's own pagination cursor, never a
user-supplied URL. The one genuinely new outbound destination is Apple's preview
host, and it is fetched by the browser rather than by the backend, so it does not
touch the server-side allowlist at all. A08 gained rather than lost: the backup
that a write is preceded by now captures the write-ahead log's committed frames,
which it did not before.

## WCAG 2.2 AA conformance statement

Every user-facing story carries accessibility acceptance criteria from phase 2.
The automated evidence is an axe-core sweep in `web/tests/e2e/accessibility.spec.ts`
and the component suites, which assert keyboard operability, focus visibility,
text-not-colour status conveyance and 24x24 minimum targets. That sweep used to run
in CI; see the second revision below for why CI is no longer evidence and what
replaced it.

Conformance is claimed for the delivered SPA at AA, with these recorded
deviations:

| Deviation | Owner | Date |
|---|---|---|
| Closed during the shell revision below: the axe sweep now loops all five workspace views rather than scanning one long page, so the review queue and the booking tree are covered. What remains open is the interaction depth inside those views, since axe scans a rendered state and does not drive the keyboard. Backlog item B6 narrows to that. | Martien | 2026-09-01 |
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

## Revision: the shell design, reviewed after the phase reopened

Phase 7 had been marked complete when the owner delivered a high-fidelity
prototype of an application shell and asked for it before approving the gate. A
re-layout of every screen invalidates two of this report's claims, the two-axis
review of the frontend tasks and the WCAG conformance statement, so the phase was
reopened rather than the report left to go stale, the design landed as phase 6
work, and this section is the review of that change. It covers commits `39d363d`
(design references and ADR 0020) through `28f476b` (the shell).

### What changed

The SPA is now the prototype's shell: a 300px sidebar and a 64px top bar in a
full-height grid, a scrolling main pane with a 1180px content column, and the
prototype's hero, stat-card, card and table styling, all from the delivered
tokens. Five workspace views rather than the prototype's three, because its three
omit US3's guarded apply, US5's collection browser and player, and US6's genre
enrichment, all of which are built: Match-overzicht carries US1 to US3, and
Koop-wachtrij, Playlist builder, Collectie and Genre-verrijking carry the rest.

Every value on screen is real. The top bar reports the Rekordbox version
`GET /api/health` returns rather than the pinned constant, and the Spotify
account actually connected; the sidebar counters come from the session and the
missing queue; the Collectie-scan card reports the real track count and drives
`POST /api/collection/reindex`, which is where the rebuild control now lives,
moved out of the table so there is exactly one.

### Two axes

Correctness against the design holds. The shell's stated dimensions, surfaces,
paddings, nav states and card styling follow HANDOFF.md. Two deviations are
deliberate and recorded in code, both in favour of accessibility the project
already claims: `--color-fog` fails AA for the small text the prototype puts it
on, so that text renders one step up in `--color-mist`, and the pipe divider is
drawn as a rule rather than a `|` glyph at `#333333` for the same reason. No
unrecorded deviation was found.

Correctness against the app holds. Nothing renders a musical key, energy value,
label, price, store grouping, format, quality, checkout, watch-folder or
XML-export affordance: a search across `web/src` for all of those returns only
comments naming the gap. That matters because the prototype specifies every one
of them and none exists in the data model or the scope, so the alternative was a
design that looked finished over an app that was not.

Design holds, with one structural improvement taken while the structure was
open: backlog item B9 is closed. Each view has a real heading outline instead of
styled paragraphs, so a screen reader finally gets an outline to navigate by.

Rule 5 is clean, checked mechanically rather than by eye: `web/src` contains no
hex colour, no arbitrary pixel value in a class name and no inline style
attribute. The one hex in the tree sits inside the comment explaining the divider
deviation. The type scale gained 10, 12, 13 and 15 pixels plus four tracking
values and a set of shell dimensions, per ADR 0020, and one colour, the
handoff's white-pill hover shade. Rule 6 holds: the only English UI strings are
the design's own section label "WORKSPACE" and the view name "Playlist builder".

### WCAG 2.2 AA, restated for the new shell

The claim is renewed rather than carried over, because the surface it describes
is new.

Contrast was computed, not assumed, for every foreground and surface pair the
shell uses. The shell renders text in exactly five colours, and the worst case of
any pair in use is 6.94:1, against a 4.5:1 requirement for small text: `mist` on
`smoke`. `bone` bottoms out at 8.43:1, `spotify-green` at 7.58:1, `pure-white` at
14.55:1, and `void-black` on the white and green pills at 10.94:1 or better.
Neither `fog` (4.16:1 at best on these surfaces) nor `steel` (2.44:1) is used for
text anywhere, which is what the recorded deviation above bought.

Target size: nav items compute to roughly 37px tall at full sidebar width, the
scan pill is 30px, the primary pill 32px, and the search submit is exactly 24x24,
which meets the minimum rather than exceeding it.

State is never conveyed by colour alone. The connection dot is `aria-hidden` and
the state it signals is spelled out in the text beside it, so "verbonden",
"niet gevonden" and "status onbekend" are readable rather than inferred from
green versus grey. The logo circle is decorative and hidden from assistive
technology; the wordmark carries the name. The green buy-queue counter is a
number, and the number is the information.

The view switcher is a `<nav>` of real buttons in a list, and the current view
carries `aria-current="page"`, verified to move when switching. The axe sweep now
loops all five views and is clean on each.

### Test evidence for this revision

`web/tests/App.test.tsx` is the guard that every story stays reachable, and it
was checked adversarially rather than trusted: removing one view from the
navigation table fails four of its tests, including the one that pins the order
of all five. The changed TrackTable and end-to-end specs kept their assertions
and gained the navigation the shell requires; the one pre-existing test whose
name promised a search it never performed now performs it.

Full state after the revision: 458 pytest, 175 vitest, 5 Playwright including two
axe sweeps, `pnpm build`, `tsc --noEmit`, ESLint and Prettier all clean, and CI
green on the branch.

### One limit on this revision, stated plainly

The independent validation pass for this change was dispatched to the
`gate-review` agent and died on a usage limit before returning. Routing rule 5
forbids answering a limit pause with a downgrade, so it was not re-run on a
smaller model. The two-axis review above therefore ran on the phase 7 model,
which is where the phase file assigns it, and builder and reviewer stay separate
because the shell was built by a different model. What is missing relative to the
eight original group reviews is the second, adversarial pair of eyes, and the
mechanical checks above exist to compensate for exactly that: contrast computed,
rule 5 grepped, the reachability guard broken on purpose to prove it bites. Worth
re-running when the window clears if the owner wants the belt and braces.

## Second revision: the delivered design, the owner's changes, and a safety fix

The first revision covered the shell. Everything below landed after it, on the
owner's instruction as they walked the delivered design point by point and then
used the result. It is reviewed here because the phase cannot sign off what it has
not looked at, and because two things in it changed decisions this report already
recorded.

Range: `28f476b..9ecc5a0`. Two independent passes reviewed it, one over the four
rebuilt views and the safety fix, one over the four backend commits the first pass
correctly noticed nobody had covered.

### What changed

Four views were rebuilt to the delivered design. The sidebar carries both playlist
sources: the operator's own Spotify playlists with their real cover art and a
status line derived from this app's sessions, and the Rekordbox library as the
expandable tree Rekordbox itself shows, where selecting a playlist filters the
collection to it. The match report gained the design's filter chips, its sort
control and its two groups, with the uncertain card showing the Rekordbox
candidate's duration, BPM and musical key. The buy queue became the design's two
columns with a store card and a summary. The builder gained phase columns, a
checks bar, and a curve card that plots BPM.

Three endpoints and a filter were added because four views needed data the API
could not answer: the operator's Spotify playlists, a Rekordbox playlist's tracks,
a structure node's stored tracks, and an `ids` filter on the collection. The last
two closed real gaps rather than conveniences: a phase's membership had only been
readable through the suggestions endpoint, which is filtered by profile and ranked
by play count, so the builder had been showing a wrongly ordered subset of what a
phase held, and it said so on screen.

Musical key and label are read from Rekordbox, verbatim in the DJ's own notation.
BPM zero now means absent, because Rekordbox stores zero for a track it has not
analysed and 85 of the 119 tracks in the owner's fixture report it: carrying it
through as a tempo had put "0 BPM" in the collection table, plotted those tracks
at the foot of the builder's chart, made a set's range read "0-120 BPM", and let
the checks bar report nothing missing a BPM while most of the set had none.

Two requirements are new and one decision was reversed, all three on the owner's
instruction. FR-041 lets the DJ hear a Missing Track before buying it and shows
its price; FR-042 opens the store link in the Music application on a Mac, at the
iTunes Store view rather than the Apple Music page. ADR 0022 supersedes ADR 0021:
playback runs through Spotify, the source the track came from, rather than the
store's own clip. That reversal cost the review queue and the buy queue their
separate players, since the SDK allows one per page, so they now share a
ref-counted singleton.

And a defect this report had listed as an open question turned out to be real. A
`master.db-wal` appeared beside the owner's fixture carrying committed data and
SQLite replayed it onto a freshly copied base file, resurrecting a playlist an
earlier apply had written. `backup.create()` zipped the base file alone, so a
backup could verify as readable while missing the newest transactions, which is
the one case backups exist for and what SC-006 claims cannot happen. It now
checkpoints a disposable staging copy and zips the self-contained result.

### Two axes

Correctness holds, and the parts that do not hold are named on screen rather than
hidden. The reviewers checked the places the implementers themselves had flagged as
approximate, and found the honesty matched by the code: the columns the design puts
on a missing track stay absent because Spotify's audio-features endpoint answers
403 for this application and the store returns no BPM or key; the curve is titled
as a BPM progression and says on the card that it is not an energy value; a track
without a BPM gets no bar rather than a fabricated one; and the key check refuses
to guess at classical notation instead of pretending to compare it.

The recurring failure mode of this codebase was hunted specifically, and four more
instances were found and fixed during this revision. A Spotify playlist whose
tracks Spotify withholds had read as an empty playlist, so a session went `ready`
with zero tracks and no message: that was the owner's first bug report, and the
cause was a `{}` default where a withheld object and an empty one were
indistinguishable. A phase whose tracks could not be read rendered as a phase
holding nothing, for all three of its documented errors. An unindexed collection
looked like an empty one. And the collection index, which is a cache rebuilt on
demand, had nothing in the app demanding it, so every fresh start showed an empty
collection with no way to fix it from the UI.

Design holds. The four views share one row type across the three endpoints that
return it, the workaround machinery that existed only because those endpoints were
missing was deleted rather than left dangling, and no state ended up owned by two
components at once. The pagination helpers three routers share moved out of one
router's private names into their own module.

Rule 5 was checked mechanically rather than by eye: `web/src` contains no hex
colour, no arbitrary pixel value in a class name and no inline style attribute, and
the tokens added trace to values the handoff actually names, including the two
stacking widths that are now tokens so the buy queue and the phase grid cannot
drift apart. Rules 1 and 2 hold across the whole tree, not only the touched files.

### The blocking finding, and why it was fixed rather than deferred

One finding was blocking, and it was the kind axe cannot see. `Tree.tsx` put
`role="tree"` and `role="treeitem"` on its rows with no key handling anywhere in
the file: no arrow keys, no roving tabindex, and no test touching either. So it
told assistive technology it was a treeview, and a screen-reader user who heard
"tree, N items" and reached for the arrow keys got nothing, while every row sat in
the page's Tab order separately. That was already true of the booking editor, and
this revision handed the same component to the sidebar's Rekordbox library, which
doubled its exposure.

This project's habit with that class of gap has been to carry it as a dated backlog
item, and the reviewer said recording it would also have closed it for the gate.
It was implemented instead: one Tab stop with a roving tabindex, arrows between
visible rows, Home and End, ArrowRight to expand or descend, ArrowLeft to collapse
or climb, Enter and Space for each variant's own action, and focus on the treeitem
itself so the role and expansion state are announced. Implementing it also
surfaced a real bug: child treeitems are genuinely nested inside their parent's
list item, so keystrokes bubbled through every ancestor and Enter on a child also
toggled the folder above it.

It was then verified in a real browser rather than only in jsdom, because the
finding was about interaction and jsdom is not that: one tab stop, arrows walking
the visible rows without wrapping, Home and End, and on a folder ArrowLeft
collapsing it, ArrowRight reopening it and ArrowRight again descending into its
first child, with `aria-expanded` following throughout.

### WCAG 2.2 AA, restated again

The claim is renewed for the surfaces this revision added: the sidebar's two lists
and its tree, the filter chips, the uncertain cards, the playback controls, the
store links, the phase columns with their keyboard move, and the BPM chart.

Contrast was computed for every new foreground and surface pair rather than
assumed, by the reviewer independently of the implementers, and every pair in use
passes AA with margin. No small text uses `--color-fog`, which fails AA on these
surfaces and is the deviation the first revision recorded.

State is never conveyed by colour alone. The move-between-phases interaction is
keyboard-operable with an announcement and focus following the moved row, which is
a genuine WCAG 2.5.7 dragging alternative rather than drag with a keyboard
afterthought. The BPM chart's bars are decoration with a real table as their text
alternative, because a row of coloured bars is not otherwise readable. The
permanent axe sweep now scans the populated review card and the populated builder,
not only their empty states, which closes the coverage half of backlog item B6.

The three deviations recorded above stand, with B6 narrowed to interaction depth:
axe scans a rendered state and does not tab through a roving-tabindex table,
resolve a review item by keyboard, or re-parent a node.

### Verification, and why CI is not part of it

CI stopped running during this revision and is not evidence any more. Both jobs
fail within seconds with zero executed steps and zero billable runner time, on
every commit and on a re-run, while the same workflow file succeeded earlier the
same day and the commits do not touch it. That is GitHub refusing to start the
jobs, most likely exhausted Actions minutes on a private repository. It is a
billing matter on the owner's account and nothing the code can fix.

So local runs are the evidence, and they were run at every step and independently
re-run by the reviewers: 534 pytest, 346 vitest, 7 Playwright specs including
three axe sweeps, plus `tsc --noEmit`, ESLint, Prettier and `pnpm build`. The two
tests that exercise the owner's real fixture were confirmed to run rather than
skip, so that count includes evidence against the real `master.db`.

Test quality was checked adversarially rather than trusted, which matters here
because this report already records a case where a test could not fail. The
reviewer checked out the commit before the backup fix and ran the new backup tests
against it: exactly the two safety-relevant tests failed, including the one that
asserts the real database is never opened for writing. The tests deleted as
workaround-pinning were checked for load-bearing coverage going with them, and
none did.

### What this revision could not verify

Three things, all stated in the code where a reader would otherwise assume
otherwise. That audio actually comes out of the Spotify path: headless Chromium
loads the SDK but cannot connect it, having no Widevine, and this container has no
Premium session and no audio output. That the `itmss` scheme opens the Music
application and lands on the Store view. And whether a live Rekordbox 7.2.17
process holds a lock or cache that would make a snapshot differ from the
checkpointed copy. All three need the Mac.

### Scope round 2, closed

Three features of the delivered design were put back on the table knowing it would
reopen phases 2 and 4: XML export, per-store checkout with purchase tracking, and
a watch folder importing purchases. The owner answered all three the same day and
none survives, so no requirement reopened and no ADR was contradicted. XML export
was dropped, which also settles its collision with ADR 0006 and SC-006. "Only
iTunes" settles per-store checkout, since grouping and totals per store only mean
something with several stores. The watch folder, the one feature that would have
had the app moving files inside the DJ's music library, the owner will handle their
own way.

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
- The two WCAG deviations above: the manual keyboard-and-target pass (B7) and the
  interaction depth axe cannot reach (B6).
- **On the Mac, three things this container cannot answer**: whether Spotify
  playback actually produces audio, whether the `itmss` link opens the Music
  application at the Store view, and whether a live Rekordbox process holds a lock
  or cache that makes a snapshot differ from the checkpointed copy. B2 itself is
  closed: Rekordbox does run `master.db` in WAL mode and the backup now
  checkpoints, so committed frames can no longer be missing from the zip.
- **The Spotify application's own permissions**, which are the hard blocker on
  proving US1 to US4 with real data. Verified against the owner's account: search
  and listing playlists work, but playlist tracks, saved tracks, audio features
  and audio analysis all answer a bare 403, the playlist response arrives with its
  tracks object stripped, and search is capped at ten results where Spotify
  documents fifty. No real playlist can reach the matcher until that is raised in
  the Spotify developer dashboard. The app now says so instead of presenting an
  empty report.
- **GitHub Actions**, so CI can be evidence again rather than local runs alone.
- **B14**, whether the buy queue should group by track. It lists a track once per
  playlist, which is right for FR-023 and useless as a shopping list past a few
  playlists: the development queue reached 158 rows for 11 distinct tracks.

## Exit criteria

| Criterion | Status |
|---|---|
| Every OWASP Top 10 item has an explicit verdict | Yes, ten verdicts above with evidence |
| WCAG 2.2 AA met, or each deviation has an owner and a date | Yes. Three deviations carry an owner and a date, and the second revision's one blocking finding, a tree claiming treeview semantics it did not implement, was fixed and verified in a real browser rather than deferred. |
| PII inventory matches what the code stores and logs, both directions | Yes, reconciled above |
| Result matches the scope note, drift written down | Yes, no drift. Two in-scope cuts recorded, and scope round 2 closed without reopening a requirement: the three design features that would have collided with ADR 0006, FR-020..023 and the library itself were all dropped by the owner. |
| `routing.py check 7` passes, every task reviewed by a non-builder | Yes |
