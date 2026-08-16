# Feature Specification: Rekordbox Companion v1

**Feature Branch**: `001-companion-v1`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Rekordbox Companion v1, specified from the confirmed
phase 1 elicitation. Sources, in order of authority:
docs/grilling/2026-08-16-phase-1.md, docs/CONTEXT.md, docs/adr/0001-0009,
specs/kickoff.md (where the grilling record corrects it, the grilling record
wins)."

Language note: this specification uses the ubiquitous language of
`docs/CONTEXT.md` (capitalised terms: Collection, Match, Apply, and the rest).
All UI copy is Dutch; this document is English per project convention.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and play the Collection (Priority: P1)

As the DJ, I search my Collection in the browser and play any Collection Track
immediately, so that I can find tracks and verify them by ear without opening
Rekordbox.

**Why this priority**: Every other feature builds on a readable Collection and
playback for verification. It is independently valuable as a fast library
browser.

**Independent Test**: With a Rekordbox database and audio files present, search
for a known track, play it, and hear audio in the browser. No Spotify or
booking features involved.

**Acceptance Scenarios**:

1. **Given** a Collection of at least 10,000 Collection Tracks, **When** the DJ
   types a search term matching artist or title, **Then** matching rows appear
   within 100 milliseconds and can be sorted by artist, title, BPM, genre and
   Play Count.
2. **Given** a Collection Track whose audio format the browser plays natively,
   **When** the DJ starts playback, **Then** audio starts and the player shows
   progress, allows pause/resume and seeking.
3. **Given** a Collection Track in a non-native format, **When** the DJ starts
   playback, **Then** the track plays through the conversion fallback with the
   same player controls.
4. **Given** a Collection Track whose audio file is missing on disk, **When**
   the DJ starts playback, **Then** the player reports in Dutch that the file
   is missing and names the expected location, and the app does not crash.

**Accessibility criteria (WCAG 2.2 AA)**:

- The track table and player are fully keyboard operable: row focus with arrow
  keys, play/pause with spacebar, seek with arrow keys when the player has
  focus.
- Focus is always visible, including on table rows and player controls.
- Text and controls meet AA contrast against the dark theme surfaces.
- All click/tap targets are at least 24x24 CSS pixels.
- The search field announces its result count to assistive technology.

---

### User Story 2 - Sync a Spotify playlist and see the match report (Priority: P1)

As the DJ, I paste a Spotify playlist URL and get a Sync Session that tells me
per track whether I own it, so that I know within a minute what a request list
means for my library.

**Why this priority**: This is the core time-saver the project exists for.

**Independent Test**: Paste a playlist URL against a fixture Collection and
verify every track lands in exactly one status bucket with plausible scores.

**Acceptance Scenarios**:

1. **Given** a valid Spotify playlist URL and a connected Spotify account,
   **When** the DJ starts a Sync Session, **Then** every Spotify Track in the
   playlist receives exactly one status: matched, review, or missing, and the
   session shows counts per status.
2. **Given** a playlist of 100 tracks, **When** the Sync Session runs, **Then**
   matching completes in under 30 seconds.
3. **Given** a Spotify Track whose normalized artist and title equal a
   Collection Track's and whose duration differs by at most 3 seconds, **When**
   matching runs, **Then** the pair is an automatic Match.
4. **Given** a Spotify Track whose best fuzzy score is at least 92 with no
   remix-marker conflict, **When** matching runs, **Then** it is an automatic
   Match; a score from 75 up to 92 puts it in the Review Queue with its top 3
   candidates; below 75 it becomes a Missing Track.
5. **Given** a Spotify Track and a Collection Track whose remix markers differ,
   **When** matching runs, **Then** the pair is never an automatic Match and
   goes to the Review Queue at best.
6. **Given** an invalid, private, or unreachable playlist URL, **When** the DJ
   starts a Sync Session, **Then** an error in Dutch names the URL field and
   states what to fix, and no session is created.
7. **Given** the Golden Set of at least 50 real match cases including at least
   10 hard cases (remixes, radio edits, featuring variants), **When** the
   matching test suite runs, **Then** every case produces its recorded expected
   outcome.

**Accessibility criteria (WCAG 2.2 AA)**:

- The URL form is keyboard submittable; its error message names the field and
  the fix in Dutch and is announced to assistive technology.
- Status counts and the per-track list are readable by screen reader with
  status conveyed as text, never by color alone.
- Focus is visible on every interactive element; targets are at least 24x24
  CSS pixels; text meets AA contrast.

---

### User Story 3 - Resolve doubtful Matches keyboard-only (Priority: P1)

As the DJ, I work through the Review Queue with only the keyboard, hearing both
the local candidate and the Spotify original, so that resolving a 100-track
playlist takes minutes, not an evening.

**Why this priority**: Fuzzy matching is the primary path (ADR 0003), so the
Review Queue carries the product's accuracy. Without it, automatic matching
alone cannot reach the accuracy goal.

**Independent Test**: Load a Sync Session with review items and resolve all of
them using only the keyboard, including listening to both versions.

**Acceptance Scenarios**:

1. **Given** a Review Queue with items, **When** the DJ navigates with arrow
   keys, **Then** up/down moves between Spotify Tracks, left/right moves
   between that track's candidates, and the focused item is visually and
   programmatically marked.
2. **Given** a focused candidate, **When** the DJ presses A, **Then** the
   candidate is accepted as the Match and focus moves to the next unresolved
   item.
3. **Given** a focused Review Queue item, **When** the DJ presses R, **Then**
   the Spotify Track is rejected, becomes a Missing Track, and focus moves to
   the next unresolved item.
4. **Given** a focused candidate, **When** the DJ presses the spacebar,
   **Then** the local candidate plays; **When** the DJ presses the
   Spotify-playback key, **Then** the Spotify original plays full-length
   through the connected Premium account; starting one stops the other.
5. **Given** an empty Review Queue, **When** the DJ opens it, **Then** a Dutch
   empty state confirms every doubtful Match is resolved.
6. **Given** a keyboard map overlay control, **When** the DJ presses the help
   key, **Then** all review shortcuts are listed in Dutch.

**Accessibility criteria (WCAG 2.2 AA)**:

- The entire review flow works without a pointing device, by definition.
- Every shortcut has a visible on-screen equivalent control (single-key
  shortcuts are remappable or only active when the queue has focus, so they
  cannot collide with assistive technology input).
- Focus is always visible; current item, candidate order and match scores are
  exposed to assistive technology as text.
- Playback state (which version is playing) is conveyed as text and icon, not
  color alone; contrast and target sizes meet AA.

---

### User Story 4 - Apply Matches to Rekordbox (Priority: P1)

As the DJ, I press one button that writes all accepted Matches of a Sync
Session into a Rekordbox playlist, so that the result is in Rekordbox the next
time I open it, without me ever fearing for my library.

**Why this priority**: Without the write-back, the match report is a read-only
curiosity. The guarded write path is also the highest-risk part of the product
and must exist early, in its final form.

**Independent Test**: Apply a session against a fixture Rekordbox database and
verify playlist content, Backup file, and readback; re-Apply after changes and
verify add-only behaviour.

**Acceptance Scenarios**:

1. **Given** a Sync Session with accepted Matches and Rekordbox not running,
   **When** the DJ Applies with a playlist name, **Then** a Backup of the
   Rekordbox database is created first, the playlist is written, read back,
   and reported with its track count, and the Backup file demonstrably exists.
2. **Given** Rekordbox is running, **When** the DJ Applies, **Then** the Guard
   refuses in Dutch, nothing is written, and no Backup is consumed as cover
   for a partial write.
3. **Given** the Rekordbox version does not match the pinned version, **When**
   the DJ Applies, **Then** the Guard refuses and names both versions.
4. **Given** a playlist this app created earlier for the same Spotify playlist,
   **When** the DJ re-Applies after a new Sync Session, **Then** only tracks
   not yet present are added; nothing is removed or reordered, including
   tracks the DJ added or removed manually in Rekordbox.
5. **Given** a bought Missing Track now present in the Collection, **When** the
   DJ runs a new Sync Session for the same playlist URL and Applies, **Then**
   the track is matched and added automatically.
6. **Given** the readback after a write does not confirm the expected playlist
   content, **When** Apply finishes, **Then** the app reports the discrepancy
   in Dutch, names the Backup file to restore, and marks the session as
   failed rather than applied.

**Accessibility criteria (WCAG 2.2 AA)**:

- Apply is reachable and operable by keyboard; its confirmation dialog traps
  focus, is dismissible with Escape, and names the playlist and track count.
- Guard refusals are announced to assistive technology and rendered as text
  meeting AA contrast; the Apply button's state (enabled, running, done,
  failed) is conveyed as text, never color alone.
- Targets are at least 24x24 CSS pixels.

---

### User Story 5 - Buy Missing Tracks via Store Links (Priority: P2)

As the DJ, I see every Missing Track with a working Store Link to the Dutch
Apple Music / iTunes Store page, so that acquiring a missing request is one
click plus a purchase.

**Why this priority**: Valuable and cheap, but only meaningful once Sync
Sessions produce Missing Tracks.

**Independent Test**: Feed a set of known missing tracks and verify link
correctness rate, statuses, and manual override.

**Acceptance Scenarios**:

1. **Given** a Missing Track, **When** the missing list loads, **Then** the
   track shows a Store Link (Dutch storefront) chosen automatically, with a
   copy button and an open-in-store action.
2. **Given** a test set of at least 30 real missing tracks, **When** links are
   generated, **Then** at least 90 percent point to the correct track page.
3. **Given** an automatically chosen Store Link that is wrong, **When** the DJ
   opens the candidate list and picks another result, **Then** the chosen link
   replaces the automatic one and both remain stored.
4. **Given** a Missing Track, **When** the DJ sets its status, **Then** open,
   acquired and ignored are available, the list is filterable by status, and
   an ignored track never reappears as open for the same Spotify Track.
5. **Given** a Missing Track with no store result, **When** the list loads,
   **Then** the row states in Dutch that no result was found and offers a
   manual search action.

**Accessibility criteria (WCAG 2.2 AA)**:

- List, filters, status changes, candidate picker and copy action are keyboard
  operable with visible focus.
- Status is conveyed as text; links have descriptive accessible names (artist
  plus title, not "link"); contrast and target sizes meet AA.

---

### User Story 6 - Enriched Genres with manual override (Priority: P2)

As the DJ, I let the app assign an Enriched Genre to Collection Tracks from
external music data and correct it where it is wrong, so that booking features
can slice a library whose own genre field is unusable.

**Why this priority**: Hard dependency of Booking Structures (ADR 0007), but
useless alone until Suggestions exist; it must land before User Story 8.

**Independent Test**: Run enrichment on a fixture Collection, measure coverage,
and override a genre manually.

**Acceptance Scenarios**:

1. **Given** a Collection Track without an Enriched Genre, **When** enrichment
   runs, **Then** the track receives zero or more Enriched Genres from
   external music data, marked with their source.
2. **Given** an enrichment run over the fixture Collection, **When** it
   completes, **Then** a coverage report states the percentage of Collection
   Tracks with at least one Enriched Genre.
3. **Given** any Collection Track, **When** the DJ sets or corrects its
   Enriched Genre by hand, **Then** the manual value wins over any source and
   survives later enrichment runs.
4. **Given** any enrichment activity, **When** it reads or writes data,
   **Then** the genre field inside Rekordbox is never modified.
5. **Given** an external source that is unreachable, **When** enrichment runs,
   **Then** it completes for the remaining sources, reports what was skipped
   in Dutch, and can be resumed later without losing prior results.

**Accessibility criteria (WCAG 2.2 AA)**:

- The genre editor is keyboard operable (open, choose, confirm, undo) with
  visible focus; form errors name the field and the fix in Dutch.
- Source and override state are conveyed as text; contrast and target sizes
  meet AA.

---

### User Story 7 - Booking Profiles (Priority: P3)

As the DJ, I define Booking Profiles (horeca, bruiloft, prive, thema) with
genre tags and optional BPM ranges, so that Suggestions can filter the
Collection per Booking Type.

**Why this priority**: Pure configuration; only meaningful together with User
Story 8.

**Independent Test**: Create, edit and delete a profile; verify its tags and
BPM ranges persist and validate.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the DJ opens profiles, **Then** the four
   Booking Types exist as seeded Booking Profiles and are editable.
2. **Given** a Booking Profile, **When** the DJ adds genre tags, **Then** tags
   are chosen from existing Enriched Genres or entered free-form, and
   duplicates within one profile are refused with a Dutch error naming the
   duplicate.
3. **Given** a Booking Profile, **When** the DJ sets a BPM range with minimum
   above maximum, **Then** the form refuses and names the field and the fix in
   Dutch.

**Accessibility criteria (WCAG 2.2 AA)**:

- Profile forms are keyboard operable with visible focus; every error names
  the field and the fix; contrast and target sizes meet AA.

---

### User Story 8 - Design and Apply a Booking Structure (Priority: P3)

As the DJ, I freely design a Booking Structure (folders and playlists: genre
and theme playlists, Set Phases vooravond/mid/prime/sluit, a Run-of-Show folder
with Moment Playlists such as openingsdans, proost and sluit), let the app
suggest tracks per playlist, curate them, and Apply the result to Rekordbox, so
that booking preparation drops from hours to minutes.

**Why this priority**: The biggest prep-time win, but it depends on Enriched
Genres, profiles, and the guarded write path already existing.

**Independent Test**: Build a structure in the editor, request Suggestions for
one playlist, curate, Apply to a fixture Rekordbox database, verify the tree.

**Acceptance Scenarios**:

1. **Given** an empty structure editor, **When** the DJ creates folders and
   playlists, renames, moves and deletes them, **Then** the tree reflects
   every action immediately and persists across app restarts, without
   touching Rekordbox.
2. **Given** a playlist in the structure linked to a Booking Profile and
   optionally a Set Phase with a BPM range, **When** the DJ requests
   Suggestions, **Then** the app proposes Collection Tracks filtered by the
   profile's genre tags and applicable BPM range, ranked by Play Count, and
   marks which are already in the structure.
3. **Given** a list of Suggestions, **When** the DJ accepts or discards each
   one, **Then** only accepted tracks are in the playlist, and nothing is
   written to Rekordbox during curation.
4. **Given** a curated Booking Structure and Rekordbox not running, **When**
   the DJ Applies it, **Then** the same Guard, Backup and readback rules as
   User Story 4 hold, and the folder and playlist tree in Rekordbox mirrors
   the editor exactly.
5. **Given** a structure whose name collides with an existing Rekordbox folder
   the app did not create, **When** the DJ Applies, **Then** the app refuses
   with a Dutch error naming the collision instead of merging into a tree it
   does not own.
6. **Given** an applied structure, **When** the DJ edits it in the companion
   and re-Applies, **Then** additions are written, and nothing is removed or
   reordered in Rekordbox (add-only, as in User Story 4).

**Accessibility criteria (WCAG 2.2 AA)**:

- The tree editor is fully keyboard operable: create, rename, move and delete
  via keys with a visible focus indicator and Dutch instructions in the
  keyboard overlay.
- Drag-and-drop, when present, has a keyboard equivalent for every operation.
- Suggestion accept/discard is keyboard operable; accepted state is text, not
  color alone; contrast and target sizes meet AA.

---

### Edge Cases

- Rekordbox is started while an Apply is in progress: the write either
  completes atomically from its pre-checked state or fails whole, with the
  Backup named; no partial playlist may remain.
- The Rekordbox database path does not exist or the decryption key is absent:
  the app starts, reports the problem in Dutch on the health surface, and all
  Rekordbox-dependent features are disabled rather than crashing.
- The Spotify session expires mid Sync Session: the session pauses, the DJ is
  asked in Dutch to reconnect, and the session resumes without losing resolved
  items.
- Two different Spotify Tracks match the same Collection Track: both Matches
  are allowed; the playlist gets the Collection Track once.
- The same Spotify playlist is synced while nothing changed on Spotify's side:
  a new Sync Session runs, previously accepted or rejected resolutions for
  identical Spotify Tracks are reused instead of re-asked.
- A Spotify playlist contains local-file tracks or podcast episodes without
  artist/title metadata usable for matching: they land as Missing Tracks with
  a Dutch note explaining why no match was attempted.
- An audio file's codec cannot be converted by the fallback: the player states
  this in Dutch and the row remains usable for everything except playback.
- The conversion fallback is unavailable on the machine: the health surface
  says so in Dutch with an installation hint, native playback keeps working.
- A Backup cannot be created (disk full, permissions): the write is refused;
  there is never a write without a fresh Backup.
- Enrichment finds conflicting genres from different sources: all are kept
  with their source; the DJ's manual choice, when present, wins.
- The DJ deletes a Booking Profile that structure playlists reference: the
  reference is cleared, the playlists and their tracks remain.

## Requirements *(mandatory)*

### Functional Requirements

Collection and playback

- **FR-001**: The system MUST read the Collection (tracks with artist, title,
  duration, BPM, genre field, Play Count, file location, and identifier) and
  the existing playlist tree from the Rekordbox database without modifying it.
- **FR-002**: The system MUST provide Collection search over artist and title
  returning results within 100 milliseconds on a 10,000-track Collection.
- **FR-003**: The system MUST stream Collection Track audio with seek support
  for natively playable formats and via a conversion fallback otherwise, and
  MUST report missing or unplayable files as such per track.
- **FR-004**: The system MUST expose a health surface reporting: Rekordbox
  database found or not, Rekordbox version matches the pinned version or not,
  conversion fallback available or not, Spotify connection state.

Matching and Sync Sessions

- **FR-005**: The system MUST let the DJ connect their own Spotify account and
  create a Sync Session from a playlist URL, fetching all its tracks.
- **FR-006**: The system MUST match every Spotify Track using this order:
  exact identifier match when both sides carry one; normalized artist+title
  equality with duration within 3 seconds; fuzzy artist+title scoring with a
  duration penalty beyond 5 seconds difference. Score at least 92 yields an
  automatic Match, 75 to below 92 yields a Review Queue entry with top 3
  candidates, below 75 yields a Missing Track.
- **FR-007**: Normalization MUST lowercase, strip featuring credits,
  remaster suffixes, bracketed content, punctuation and diacritics, and keep
  remix/edit markers as a separate comparison token.
- **FR-008**: Differing remix/edit markers MUST prevent automatic matching;
  such pairs go to the Review Queue at best (remix guard).
- **FR-009**: The Review Queue MUST be operable keyboard-only: arrow
  navigation, A accepts the focused candidate, R rejects the Spotify Track,
  spacebar plays the local candidate, a dedicated key plays the Spotify
  original full-length via the DJ's Premium account; starting either playback
  stops the other.
- **FR-010**: A rejected Spotify Track MUST become a Missing Track.
- **FR-011**: Re-syncing a playlist URL MUST reuse the DJ's previous accept
  and reject resolutions for identical Spotify Tracks within that playlist's
  sessions.
- **FR-012**: The system MUST maintain the Golden Set as an extend-only
  fixture: removing or weakening a recorded case MUST fail the build.

Writing to Rekordbox

- **FR-013**: Every write to the Rekordbox database MUST be preceded, in
  order, by: a Guard check that Rekordbox is not running and that its version
  equals the pinned version, then a timestamped Backup of the database. After
  the write, the system MUST read back and verify what was written; on
  discrepancy it MUST report failure and name the Backup.
- **FR-014**: Applying a Sync Session MUST create one Rekordbox playlist
  (name chosen by the DJ, optional parent folder) containing all accepted
  Matches, and remember which Rekordbox playlist belongs to which Spotify
  playlist.
- **FR-015**: Applying for a Spotify playlist that already has a
  companion-created Rekordbox playlist MUST add missing tracks only, and MUST
  NOT remove or reorder anything in that playlist.
- **FR-016**: Writes to Rekordbox are limited to creating playlists and
  folders and adding tracks to companion-created playlists. The system MUST
  NOT modify track metadata, existing foreign playlists, or any other
  Rekordbox data.

Missing Tracks and Store Links

- **FR-017**: The system MUST look up each Missing Track on the Dutch Apple
  Music / iTunes storefront, store the automatically chosen Store Link,
  present alternative candidates for manual override, and keep both automatic
  and chosen links.
- **FR-018**: Missing Tracks MUST carry status open, acquired or ignored,
  settable by the DJ, filterable, with copy and open actions per link. An
  ignored Spotify Track MUST NOT return as open in later sessions of the same
  playlist.
- **FR-019**: The system MUST support re-running store lookups on demand for
  unresolved Missing Tracks.

Enriched Genres

- **FR-020**: The system MUST enrich Collection Tracks with Enriched Genres
  from at least one external music data source, store them with their source
  in its own data store, and never write genre data into Rekordbox.
- **FR-021**: The DJ MUST be able to set or correct Enriched Genres manually;
  a manual value MUST take precedence over sourced values and survive later
  enrichment runs.
- **FR-022**: Enrichment MUST be resumable: interruption or source failure
  loses no prior results, and a coverage report (percentage of Collection
  Tracks with at least one Enriched Genre) MUST be available after each run.

Booking Profiles and Structures

- **FR-023**: The system MUST seed the four Booking Types (horeca, bruiloft,
  prive, thema) as editable Booking Profiles with genre tags and optional BPM
  ranges, validating that BPM minimum does not exceed maximum and refusing
  duplicate tags per profile.
- **FR-024**: The system MUST provide a structure editor where the DJ freely
  creates, renames, moves and deletes folders and playlists, persisted in the
  companion and written to Rekordbox only on Apply.
- **FR-025**: For a structure playlist, the system MUST generate Suggestions:
  Collection Tracks filtered by the linked Booking Profile's genre tags
  (against Enriched Genres) and applicable BPM range, ranked by Play Count
  descending, individually acceptable or discardable before anything is
  written.
- **FR-026**: Applying a Booking Structure MUST follow FR-013, create the
  folder and playlist tree exactly as designed, refuse on a name collision
  with a tree the companion does not own, and behave add-only on re-Apply.

Cross-cutting

- **FR-027**: The app MUST be reachable only from the machine it runs on; no
  remote network access is offered.
- **FR-028**: All UI copy MUST be Dutch, including empty states, errors and
  the keyboard overlay; every error that concerns a form MUST name the field
  and the fix.
- **FR-029**: Every user-facing view MUST meet the accessibility criteria
  listed per user story (keyboard operability, visible focus, AA contrast,
  24x24 CSS pixel minimum targets, assistive-technology announcements).
- **FR-030**: The system MUST keep the DJ's Spotify credentials and tokens
  only on the local machine, and support disconnecting, which deletes them.

### Key Entities

- **Collection Track**: A track in the Rekordbox library; identity, artist,
  title, duration, BPM, file location, Play Count. Read-only source data.
- **Sync Session**: One matching run of one Spotify playlist against the
  Collection; owns its Spotify Tracks and their outcomes; remembers the
  target Rekordbox playlist it created or updates.
- **Spotify Track**: A track from the fetched playlist; artist, title,
  duration, identifiers; carries one status within its session.
- **Match**: Pairing of Spotify Track and Collection Track with score and
  origin (automatic or accepted in review).
- **Missing Track**: A Spotify Track without accepted Match; carries Store
  Links (automatic and chosen) and status open/acquired/ignored.
- **Enriched Genre**: Genre value for a Collection Track with source
  (external source name or manual); lives only in the companion.
- **Booking Profile**: Named per Booking Type; genre tags and optional BPM
  ranges.
- **Booking Structure**: DJ-designed tree of folders and playlists; playlists
  optionally linked to a Booking Profile and Set Phase; tracks curated from
  Suggestions; Apply state per node.
- **Backup**: Timestamped copy of the Rekordbox database, created before
  every write, listed and named in failure reports.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Matching a 100-track playlist completes in under 30 seconds.
- **SC-002**: On the Golden Set, 100 percent of recorded expected outcomes are
  reproduced; on a well-tagged reference playlist, at least 95 percent of
  automatic Matches are correct.
- **SC-003**: Collection search returns results within 100 milliseconds on a
  10,000-track Collection.
- **SC-004**: At least 90 percent of Missing Tracks in the reference test set
  resolve to a correct Store Link automatically.
- **SC-005**: Zero writes to the Rekordbox database ever occur without a
  fresh Backup existing first, demonstrable in tests and logs.
- **SC-006**: The DJ resolves a 20-item Review Queue, including listening to
  both versions where needed, in under 10 minutes using only the keyboard.
- **SC-007**: Preparing the playlist side of a booking (sync, review, apply,
  missing list) takes under 30 minutes end to end for a typical 100-track
  request list, down from hours today.
- **SC-008**: After enrichment, at least 80 percent of Collection Tracks
  carry at least one Enriched Genre, measured on the fixture Collection (if
  the sources structurally cannot reach this on the real library, that is a
  recorded finding for the owner, not a silent pass).

## Assumptions

- The single operator is the machine's only user; OS-level login is the
  access control (ADR 0001); no in-app authentication exists.
- Rekordbox stays pinned at the recorded version for the project duration
  (ADR 0002); the health surface warns on drift.
- The owner supplies before implementation: a fixture copy of the Rekordbox
  database, a Spotify application client id, and confirmation that the
  database decryption key was obtained on the Mac (grilling D10).
- The owner's Spotify Premium subscription remains active; full-length
  Spotify playback in review degrades to unavailable without it (ADR 0009).
- External store and music-data lookups are best effort against live
  services; rate limits pace the work rather than fail it.
- Structure templates, play-history analysis, waveforms, auto-watching
  playlists, cloud deployment, audio downloading and Rekordbox metadata
  editing are out of scope for v1 (kickoff non-goals; grilling D8 defers
  templates).
- UI copy is Dutch; code, documentation and this spec are English.

## PII Inventory

The inventory lives next to this spec in
`specs/001-companion-v1/pii-inventory.md`: four elements (Spotify OAuth
tokens, Spotify account id and playlist contents, the owner's own library and
play data, store lookup search terms), each with lawful basis, retention and
processors. All data belongs to the single operator; no analytics, no
telemetry, no third-party storage. A change that adds any personal data
element MUST extend that inventory in the same change.
