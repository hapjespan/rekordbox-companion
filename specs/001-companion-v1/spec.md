# Feature Specification: Rekordbox Companion v1

**Feature Branch**: `001-companion-v1`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Rekordbox Companion v1: a local-first web app for a single working DJ, per specs/kickoff.md as corrected by docs/grilling/2026-08-16-phase-1.md and the glossary in docs/CONTEXT.md."

Terminology in this document follows the glossary in `docs/CONTEXT.md`. Capitalised
terms (Collection, Sync Session, Match, Review Queue, Missing Track, Apply, Guard,
Backup, Booking Structure, Suggestion, Enriched Genre, Target Playlist) are defined
there.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Instant match report for a Spotify playlist (Priority: P1)

The DJ pastes a Spotify playlist URL into the companion and, without any further
input, sees a report of every track in that playlist classified as matched
(already in the Collection), doubtful (needs review), or missing (not in the
Collection). This is the core question the product answers: "what do I already
own?"

**Why this priority**: Every other feature consumes this result. Without the
match report there is no review, no apply, no missing queue. It is the single
scenario that proves the idea has value.

**Independent Test**: Can be fully tested by pasting a known playlist URL against
a fixture Collection and checking the classification counts and per-track
classifications against expected outcomes, without any write path or review UI
existing.

**Acceptance Scenarios**:

1. **Given** a connected Spotify account and an indexed Collection, **When** the
   DJ pastes a valid Spotify playlist URL and starts a Sync Session, **Then**
   every track in the playlist receives exactly one status: matched, review, or
   missing, and the report shows totals per status.
2. **Given** a playlist of 100 tracks, **When** a Sync Session runs, **Then** the
   full report is visible within 30 seconds.
3. **Given** a Spotify Track whose identifier (ISRC) exactly equals a Collection
   Track's identifier, **When** matching runs, **Then** it auto-matches without
   review.
4. **Given** a Spotify Track whose normalised artist and title exactly equal a
   Collection Track's and whose duration differs by at most 3 seconds, **When**
   matching runs, **Then** it auto-matches without review.
5. **Given** a Spotify Track that only matches fuzzily, **When** its combined
   similarity score is at or above the auto-match bar (92), **Then** it
   auto-matches; **When** the score is between 75 and 92, **Then** it enters the
   Review Queue with its top 3 candidate Collection Tracks; **When** the score is
   below 75, **Then** it becomes a Missing Track.
6. **Given** a Spotify Track and a candidate Collection Track whose remix/edit
   markers differ (for example "Club Mix" versus original), **When** matching
   runs, **Then** the pair never auto-matches regardless of score and is forced
   into the Review Queue.
7. **Given** an invalid, private, or unreachable playlist URL, **When** the DJ
   submits it, **Then** the report does not start and an error names the URL
   field and states what to fix (for example: playlist is private, or URL is not
   a Spotify playlist link).
8. **Given** the Golden Set of at least 50 real match cases including at least 10
   hard cases (remixes, radio edits, featuring variants), **When** the matching
   pipeline runs against it, **Then** every case produces its expected outcome.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- The URL input, submit action and report are fully operable by keyboard alone.
- Focus is always visible on the input and on every interactive element of the
  report.
- Status classifications are distinguishable by text, not by colour alone, and
  all text meets AA contrast against its surface.
- All interactive targets are at least 24x24 CSS pixels.
- The URL error message names the field and the fix, and is announced to
  assistive technology.

---

### User Story 2 - Keyboard-first review of doubtful matches (Priority: P2)

The DJ walks the Review Queue of a Sync Session and resolves every doubtful Match
without touching the mouse: arrow keys move through queue and candidates, A
accepts the selected candidate, R rejects (none of the candidates is the
requested track), and space previews. To judge a match by ear the DJ can play
both sides: the Collection Track streams locally, and the Spotify original plays
full-length through the DJ's own Spotify Premium account, inside the review
screen.

**Why this priority**: Fuzzy matching is the primary path for this library, so
the review flow carries the product's accuracy. It converts a good match report
into a trustworthy one.

**Independent Test**: Can be tested with a seeded Review Queue: every queue item
can be resolved to accepted or rejected using only the documented keys, and both
audio sources are playable per item.

**Acceptance Scenarios**:

1. **Given** a Sync Session with doubtful Matches, **When** the DJ opens the
   Review Queue, **Then** each item shows the Spotify Track and up to 3 candidate
   Collection Tracks with their scores, and the first item holds focus.
2. **Given** a focused queue item, **When** the DJ presses A on a selected
   candidate, **Then** that candidate becomes the accepted Match and focus moves
   to the next unresolved item.
3. **Given** a focused queue item, **When** the DJ presses R, **Then** the
   Spotify Track becomes a Missing Track (reject means "wrong match", never "do
   not want") and focus moves to the next unresolved item.
4. **Given** a focused candidate Collection Track, **When** the DJ presses space,
   **Then** the local audio plays; **Given** the Spotify side is selected,
   **When** the DJ triggers playback, **Then** the full Spotify track plays via
   the DJ's Premium account inside the review screen.
5. **Given** an accepted or rejected item, **When** the DJ re-opens the Sync
   Session later, **Then** the resolution is preserved.
6. **Given** the last unresolved item is resolved, **When** the queue is empty,
   **Then** the DJ sees a completion state with the updated session totals.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- The entire review flow is operable by keyboard alone; the documented key map
  (arrows, A, R, space) is discoverable from the screen.
- Focus is always visible and never lost when an item is resolved.
- Scores and match status are conveyed in text with AA contrast, not by colour
  alone.
- All interactive targets are at least 24x24 CSS pixels.
- Playback controls expose accessible names and states (playing/paused) to
  assistive technology.

---

### User Story 3 - Apply matches to Rekordbox, guarded (Priority: P3)

With one action the DJ writes all accepted Matches of a Sync Session into
Rekordbox as a playlist. The write is guarded: it is refused while Rekordbox is
running or when the installed Rekordbox version is not the pinned 7.2.17, a
timestamped Backup of the Rekordbox database is taken before the write, and the
result is verified by reading it back. Re-running the same Spotify playlist URL
later updates the same Target Playlist add-only: tracks are only ever added,
never removed or reordered.

**Why this priority**: This is where saved time becomes real (the playlist
appears in Rekordbox), and where the irreplaceable library is at stake, so the
safety behaviour is part of the story, not an implementation detail.

**Independent Test**: Can be tested against a fixture copy of the Rekordbox
database: apply writes the expected playlist, a backup file exists per write,
readback confirms content, a second apply of a re-synced session adds only new
tracks, and apply is refused when the guard conditions fail.

**Acceptance Scenarios**:

1. **Given** a Sync Session with accepted Matches and a closed Rekordbox at the
   pinned version, **When** the DJ applies with a playlist name, **Then** a
   Backup is created first, the playlist is written, readback verification
   confirms every accepted Match is present, and the DJ sees confirmation with
   the backup's timestamp.
2. **Given** Rekordbox is running, **When** the DJ attempts Apply, **Then** the
   write is refused before anything is touched and the message tells the DJ to
   close Rekordbox and retry.
3. **Given** an installed Rekordbox version other than 7.2.17, **When** the DJ
   attempts Apply, **Then** the write is refused and the message names the found
   and the required version.
4. **Given** a Spotify playlist URL that was applied before, **When** the DJ
   re-syncs the same URL and applies again, **Then** the same Target Playlist is
   updated, newly accepted tracks are appended, and no track is removed or
   reordered.
5. **Given** the Target Playlist was deleted inside Rekordbox since the last
   apply, **When** the DJ applies, **Then** the companion detects the missing
   Target Playlist, creates it anew, and reports that it did so.
6. **Given** any write, **When** it completes, **Then** exactly one new Backup
   with a timestamp exists for that write, without exception.
7. **Given** readback verification fails after a write, **When** Apply reports,
   **Then** the DJ is told verification failed, which Backup to restore, and the
   session is not marked applied.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- The apply action, its confirmation dialog and its result state are operable by
  keyboard alone with visible focus.
- Refusal and failure messages name the blocking condition and the fix, in text
  meeting AA contrast.
- The playlist name input reports errors by naming the field and the fix.
- All interactive targets are at least 24x24 CSS pixels.

---

### User Story 4 - Missing tracks become purchases (Priority: P4)

Every Spotify Track without an accepted Match lands in the missing queue, where
each row carries a Store Link to the exact track page in the Apple Music / iTunes
Store, Dutch storefront. The DJ tracks each Missing Track as open, acquired, or
ignored ("do not want"). When the DJ has bought a track and re-syncs the same
playlist URL, the bought track matches automatically and leaves the missing
queue.

**Why this priority**: It closes the loop from "what am I missing" to "go get
it", the second half of the product's core question, but it depends on the match
report existing.

**Independent Test**: Can be tested with a seeded missing queue: links resolve to
the correct NL storefront pages for a test set, statuses are settable and
persistent, and a re-sync against an updated fixture Collection moves an
acquired track out of the queue.

**Acceptance Scenarios**:

1. **Given** a completed Sync Session with Missing Tracks, **When** the DJ opens
   the missing queue, **Then** each row shows artist, title, status and a Store
   Link to the NL storefront, with a copy action for the link.
2. **Given** an automatic Store Link lookup that picked the wrong track page,
   **When** the DJ overrides it manually, **Then** the chosen link is stored and
   shown instead, and the automatic pick remains recorded.
3. **Given** a Missing Track the DJ does not want, **When** the DJ sets it to
   ignored, **Then** it leaves the default view and is never re-added as open by
   a later sync of the same playlist.
4. **Given** a Missing Track whose audio the DJ has since added to the
   Collection, **When** the DJ re-syncs the same playlist URL, **Then** the track
   matches automatically and the Missing Track is closed.
5. **Given** a lookup that finds no store page, **When** the queue renders,
   **Then** the row says no link was found and offers the manual override.
6. **Given** a test set of at least 20 missing tracks, **When** links are
   resolved, **Then** at least 90% point to the correct track page.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- Queue navigation, status changes, link copy and manual override are operable
  by keyboard alone with visible focus.
- Status is conveyed in text, not by colour alone, at AA contrast.
- All interactive targets are at least 24x24 CSS pixels.
- The manual override input reports errors by naming the field and the fix.

---

### User Story 5 - Browse and play the Collection (Priority: P5)

The DJ searches and sorts the full Collection (30.000+ tracks) in the browser and
plays any Collection Track directly, to verify matches by ear and to explore the
library. Playback covers the library's native formats and falls back to
server-side conversion for formats the browser cannot play directly.

**Why this priority**: It is the workbench under the other stories (review
preview, suggestion curation) and useful on its own, but it answers no booking
question by itself.

**Independent Test**: Can be tested standalone against a fixture Collection:
search returns expected tracks fast, both native formats play, and the
conversion fallback passes against a non-native fixture file.

**Acceptance Scenarios**:

1. **Given** an indexed Collection of at least 30.000 tracks, **When** the DJ
   types in the search field, **Then** matching tracks (artist, title) appear
   within 100 milliseconds per keystroke.
2. **Given** the track table, **When** the DJ sorts by artist, title, BPM or
   Play Count, **Then** the order updates accordingly.
3. **Given** any mp3 or m4a Collection Track from the library, **When** the DJ
   plays it, **Then** audio starts and the player shows progress and allows
   seeking.
4. **Given** a Collection Track in a format the browser cannot play natively,
   **When** the DJ plays it, **Then** the conversion fallback streams it
   transparently.
5. **Given** a Collection Track whose audio file is missing on disk, **When**
   the DJ plays it, **Then** the player reports the file as missing instead of
   failing silently.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- Search, table navigation, sort and player controls are operable by keyboard
  alone with visible focus.
- The table remains readable at AA contrast in its dense layout.
- All interactive targets, including player controls, are at least 24x24 CSS
  pixels.
- Player state (playing, paused, seeking position) is exposed to assistive
  technology.

---

### User Story 6 - Enriched genres with manual override (Priority: P6)

The companion assigns each Collection Track one or more Enriched Genres sourced
from external music data, because the genre field inside Rekordbox is messy and
mostly empty. The DJ can correct any track's Enriched Genres by hand, and the
correction wins permanently. Rekordbox's own metadata is never written. Enriched
Genres exist to drive booking Suggestions and are a hard prerequisite for User
Story 7.

**Why this priority**: Load-bearing for the booking feature, worthless to a
booking without Story 7 shipped; it must land before Story 7 but has no
standalone booking value.

**Independent Test**: Can be tested by enriching a fixture Collection, measuring
coverage, exercising the manual override, and confirming the Rekordbox database
bytes are untouched afterwards.

**Acceptance Scenarios**:

1. **Given** an indexed Collection, **When** enrichment runs, **Then** at least
   80% of Collection Tracks carry at least one Enriched Genre.
2. **Given** an enriched Collection Track, **When** the DJ edits its genres
   manually, **Then** the manual value is stored, marked as manual, and never
   overwritten by a later enrichment run.
3. **Given** a track the external sources know nothing about, **When**
   enrichment runs, **Then** the track is marked unenriched and appears in a
   list the DJ can work through manually.
4. **Given** any enrichment run, **When** it completes, **Then** the Rekordbox
   database is byte-for-byte unchanged.
5. **Given** a sample of 50 enriched tracks reviewed by the DJ, **When** the DJ
   judges the assigned genres, **Then** at least 90% are judged usable for
   booking filtering.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- Genre viewing and editing are operable by keyboard alone with visible focus.
- Manual-versus-automatic origin is conveyed in text, not by colour alone, at AA
  contrast.
- All interactive targets are at least 24x24 CSS pixels.
- The genre edit input reports errors by naming the field and the fix.

---

### User Story 7 - Hand-designed booking structures with curated suggestions (Priority: P7)

The DJ designs a Booking Structure freely in the companion: a tree of folders and
playlists, typically genre and theme playlists subdivided by Set Phase
(vooravond, mid, prime, sluit) plus a Run-of-Show folder with Moment Playlists
(openingsdans, proost, sluit). For each playlist in the structure the companion
offers ranked Suggestions: Collection Tracks filtered by the Booking Profile's
genre tags and optional BPM ranges, ranked by Play Count. The DJ curates the
Suggestions per playlist, then Applies the whole structure to Rekordbox through
the same guarded write path as Story 3. The companion never generates a
structure on its own.

**Why this priority**: The biggest time saver for booking prep, but it consumes
everything before it: the Collection index, Enriched Genres, and the guarded
write path.

**Independent Test**: Can be tested by building a structure against a fixture
Collection with seeded Enriched Genres: suggestions honour the profile's filters
and rank by Play Count, curation is editable, and apply writes the expected
folder and playlist tree to a fixture Rekordbox database.

**Acceptance Scenarios**:

1. **Given** the seeded Booking Profiles (horeca, bruiloft, prive, thema),
   **When** the DJ edits a profile's genre tags and BPM ranges, **Then** the
   changes persist and drive subsequent Suggestions.
2. **Given** an empty workspace, **When** the DJ creates folders and playlists
   and nests, renames, moves or deletes them, **Then** the tree reflects every
   edit and persists between visits.
3. **Given** a playlist in the structure and a selected Booking Profile,
   **When** the DJ requests Suggestions, **Then** the companion lists Collection
   Tracks that pass the profile's genre and BPM filters, ordered by Play Count
   descending, and marks which ones are already in the playlist.
4. **Given** a Suggestion list, **When** the DJ accepts some and dismisses
   others, **Then** only accepted tracks enter the playlist and dismissed ones
   do not return for that playlist.
5. **Given** a finished structure and a closed Rekordbox at the pinned version,
   **When** the DJ applies it, **Then** the guard, Backup and readback sequence
   of Story 3 runs and the full folder and playlist tree appears in Rekordbox.
6. **Given** a structure that was applied before, **When** the DJ applies it
   again after edits, **Then** companion-created folders and playlists are
   updated add-only: new items and tracks are added, nothing is removed or
   reordered in Rekordbox.

**Accessibility acceptance criteria (WCAG 2.2 AA)**:

- Tree editing, suggestion review and curation are operable by keyboard alone
  with visible focus.
- Accepted/dismissed/already-present states are conveyed in text, not by colour
  alone, at AA contrast.
- All interactive targets are at least 24x24 CSS pixels.
- Naming inputs (folders, playlists) report errors by naming the field and the
  fix.

---

### Edge Cases

- A Spotify playlist longer than 999 tracks: the Sync Session is refused
  before it starts, with a message naming the limit (phase 3 constraint, D12).
- A Spotify playlist contains the same track twice: the Sync Session reports it
  once per playlist position, but Apply writes it to the Target Playlist only
  once.
- A Spotify playlist contains a local file or an unavailable track (no usable
  identifiers): the track is reported as unmatchable and counted separately, not
  silently dropped.
- Two Collection Tracks are near-identical duplicates: both may appear as
  candidates in the Review Queue; accepting one never auto-resolves the other.
- The Spotify session expires mid Sync Session: the session fails with a
  re-connect prompt and no partial report is presented as complete.
- The DJ manually removed a track from the Target Playlist inside Rekordbox:
  the next Apply re-adds it, because Apply guarantees every accepted Match is
  present and never interprets absence as intent.
- The Rekordbox database file is not at its expected location: the app starts in
  a degraded state that names the expected path and blocks all Rekordbox-backed
  features instead of erroring per screen.
- Disk space is insufficient for a Backup: Apply is refused before any write.
- A Collection Track's BPM is absent: BPM filters treat it as not passing, and
  the suggestion screen says how many tracks were excluded for missing BPM.
- The playback and enrichment features are used while a Sync Session runs:
  read-only features stay available during matching.
- An enrichment source is unreachable: enrichment reports partial completion and
  can resume; it never blocks the rest of the app.
- The DJ renames a structure node that was already applied to Rekordbox: the
  companion refuses with a message naming the rule; names of applied nodes are
  owned by Rekordbox from the first Apply on.

## Requirements *(mandatory)*

### Functional Requirements

**Spotify sync and matching**

- **FR-001**: The system MUST let the DJ connect their own Spotify account once
  and reuse that authorisation for playlist fetching and in-app playback until
  the DJ disconnects it.
- **FR-002**: The system MUST accept a Spotify playlist URL and create a Sync
  Session that fetches all playlist tracks and matches each against the
  Collection. Selecting one of the operator's own Spotify playlists from a list
  is a second way to reach the same Sync Session and creates nothing new: the
  selection resolves to that playlist's URL and takes the identical path.
  Recorded 2026-08-19 after a gate review noted the affordance existed in the
  code and the contract without a sentence here saying it is presentation over
  this requirement rather than a requirement of its own.
- **FR-003**: The system MUST classify every track of a Sync Session as exactly
  one of: matched, review, or missing.
- **FR-004**: The system MUST normalise artist and title before comparison:
  case-insensitive, featuring credits, remaster suffixes, bracketed additions,
  punctuation and diacritics stripped, with remix/edit markers kept aside as a
  distinct comparison token.
- **FR-005**: The system MUST auto-match on exact identifier (ISRC) equality when
  both sides carry one.
- **FR-006**: The system MUST auto-match on exact normalised artist+title
  equality when durations differ by at most 3 seconds.
- **FR-007**: The system MUST score remaining pairs by fuzzy similarity over
  artist and title, weighted 40% artist and 60% title, with a duration penalty
  beyond 5 seconds difference; scores of 92 or higher auto-match, scores from 75
  up to 92 enter the Review Queue with the top 3 candidates, scores below 75
  become Missing Tracks.
- **FR-008**: The system MUST never auto-match a pair whose remix/edit markers
  differ; such pairs are forced into the Review Queue.
- **FR-009**: The system MUST validate every matching pipeline change against
  the Golden Set; the Golden Set MUST only ever be extended, never weakened.
- **FR-010**: The system MUST re-use one Sync Session lineage per Spotify
  playlist URL, so a re-run updates the same Target Playlist and re-evaluates
  previously missing tracks.

**Review**

- **FR-011**: The system MUST present doubtful Matches in a Review Queue
  resolvable entirely by keyboard: navigate (arrow keys), accept (A), reject
  (R), preview (space).
- **FR-012**: The system MUST treat reject as "wrong match": the rejected
  Spotify Track becomes a Missing Track. The intent "I do not want this track"
  MUST be expressed by ignoring the Missing Track, never by reject.
- **FR-013**: The system MUST let the DJ hear both sides of a doubtful Match:
  the candidate Collection Track via local streaming and the Spotify original
  full-length via the DJ's Premium account, inside the review screen.
- **FR-014**: The system MUST persist every review resolution immediately.

**Writing to Rekordbox**

- **FR-015**: The system MUST refuse any write to the Rekordbox database while
  Rekordbox is running or when the installed version differs from the pinned
  7.2.17, and MUST say which condition blocked the write.
- **FR-016**: The system MUST create a timestamped Backup of the Rekordbox
  database before every write, without exception, and MUST verify every write by
  reading it back.
- **FR-017**: The system MUST write only playlists and folders to Rekordbox. It
  MUST never edit track metadata, cues, or beat grids, and never delete or
  reorder anything it did not just create.
- **FR-018**: The system MUST update companion-created playlists and folders
  add-only on re-apply: additions only, no removals, no reordering.
- **FR-019**: The system MUST keep the association between a Spotify playlist
  URL and its Target Playlist, detect a Target Playlist deleted inside
  Rekordbox, and recreate it on the next Apply while telling the DJ.

**Missing tracks**

- **FR-020**: The system MUST list all Missing Tracks with a Store Link to the
  exact track page on the Apple Music / iTunes Store, Dutch storefront, with a
  copy action.
- **FR-021**: The system MUST track Missing Track status as open, acquired, or
  ignored, persistently.
- **FR-022**: The system MUST allow a manual Store Link override per Missing
  Track and keep both the automatic and the chosen link.
- **FR-023**: The system MUST close a Missing Track automatically when a later
  Sync Session of the same playlist URL matches it against the Collection.
- **FR-041**: The system MUST let the DJ hear a Missing Track before buying it,
  by playing the store's own preview of the exact track the Store Link leads to,
  and MUST show that track's price beside the link. A track without a preview or
  without a price says so rather than offering a dead control. Added 2026-08-19
  on the owner's request after first real use: deciding what to buy from artist
  and title alone is guesswork, and the preview, the price and the link all
  arrive in the store lookup the app already performs, so this costs no new
  service, credential or outbound host.
- **FR-042**: On macOS the Store Link MUST be openable in the Music application
  rather than the browser, since the browser only offers excerpts of what the
  Music app plays and sells in full. The same store page serves both: swapping
  `https` for the `itmss` scheme on a `music.apple.com` URL hands it to the Music
  app, so the app keeps one stored link and offers both destinations. The browser
  route stays available, because the app is developed and can be viewed on
  machines where no Music application exists. Added 2026-08-19 on the owner's
  request, in place of the design's per-store checkout, which they dropped in
  favour of iTunes alone.

**Collection and playback**

- **FR-024**: The system MUST provide search over artist and title and sorting
  over artist, title, BPM and Play Count across the full Collection, responsive
  at 30.000+ tracks and tested at 40.000.
- **FR-025**: The system MUST stream and play any Collection Track in the
  browser, with seek support, covering the library's native formats directly
  and other formats through a conversion fallback.
- **FR-026**: The system MUST report a missing or unreadable audio file as such
  in the player instead of failing silently.

**Genre enrichment**

- **FR-027**: The system MUST assign Enriched Genres to Collection Tracks from
  external music data sources, stored inside the companion only.
- **FR-028**: The system MUST let the DJ override any track's Enriched Genres
  manually; a manual value wins over every later enrichment run.
- **FR-029**: The system MUST list tracks that received no Enriched Genre so the
  DJ can complete them manually.
- **FR-030**: The system MUST never write genre data, or any enrichment output,
  into the Rekordbox database.

**Booking structures**

- **FR-031**: The system MUST provide Booking Profiles, seeded with horeca,
  bruiloft, prive and thema, each carrying editable genre tags and optional BPM
  ranges.
- **FR-032**: The system MUST let the DJ freely create, rename, nest, move and
  delete folders and playlists in a Booking Structure workspace, persistently.
  A node that has been applied to Rekordbox is rename-locked in the companion;
  renaming it afterwards is done in Rekordbox itself (owner decision, phase 4
  grilling).
- **FR-033**: The system MUST offer Suggestions per structure playlist:
  Collection Tracks filtered by the selected Booking Profile's genre tags
  (against Enriched Genres) and BPM ranges, ranked by Play Count descending.
- **FR-034**: The system MUST let the DJ accept or dismiss Suggestions per
  playlist; dismissed Suggestions do not return for that playlist; nothing
  enters a playlist uncurated.
- **FR-035**: The system MUST Apply a Booking Structure to Rekordbox through the
  same guarded path as sync results (FR-015 through FR-018).
- **FR-036**: The system MUST NOT auto-generate structures; the structure's
  shape is exclusively the DJ's.

**Cross-cutting**

- **FR-037**: The system MUST be reachable only from the machine it runs on; no
  remote or multi-user access exists in v1.
- **FR-038**: All user-facing text MUST be in Dutch.
- **FR-039**: Every rendered colour, typography, spacing and radius value MUST
  trace to the delivered design token set; the proprietary SpotifyMixUI font
  MUST never ship, its substitute serving under the original token names.
- **FR-040**: The system MUST keep read-only features usable while a Sync
  Session or enrichment run is in progress.

### Key Entities

- **Collection Track**: a track in the DJ's Rekordbox library, referenced by its
  Rekordbox content id; carries artist, title, duration, BPM, Play Count,
  location, and app-side Enriched Genres. The companion never duplicates the
  Rekordbox data wholesale; it references it.
- **Sync Session**: one run of fetching a Spotify playlist and matching it;
  linked to the playlist URL lineage so re-runs update the same Target Playlist.
- **Match**: pairing of one Spotify Track with one Collection Track plus a
  score; automatic or reviewed; resolution states matched, review, missing,
  rejected.
- **Missing Track**: a Spotify Track without an accepted Match; status open,
  acquired or ignored; carries automatic and optional manual Store Link.
- **Target Playlist**: the companion-created Rekordbox playlist a playlist URL's
  Applies write to, always the same one per URL, updated add-only.
- **Enriched Genre**: app-side genre assignment per Collection Track; automatic
  (from external sources) or manual (DJ override, permanent).
- **Booking Profile**: named booking type (horeca, bruiloft, prive, thema) with
  genre tags and optional BPM ranges; drives Suggestion filtering.
- **Booking Structure**: DJ-designed tree of folders and playlists, including
  Set Phase subdivisions and a Run-of-Show folder with Moment Playlists;
  applied to Rekordbox add-only.
- **Suggestion**: a proposed Collection Track for one structure playlist, ranked
  by Play Count, filtered by profile; accepted or dismissed per playlist.
- **Backup**: timestamped copy of the Rekordbox database, one per write, kept
  locally.
- **Golden Set**: fixed, growing set of real match cases with expected outcomes
  gating every matching change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 100-track Spotify playlist produces a complete match report in
  under 30 seconds.
- **SC-002**: At least 95% of automatic matches are correct, measured against
  the Golden Set and spot checks on real playlists.
- **SC-003**: The Golden Set holds at least 50 real cases, at least 10 of them
  hard (remix, radio edit, featuring variants), and passes at 100% on every
  matching change.
- **SC-004**: At least 90% of Missing Tracks in a 20+ track test set resolve to
  the correct NL store page automatically.
- **SC-005**: Collection search feels instant: results within 100 milliseconds
  per keystroke on a 30.000+ track Collection.
- **SC-006**: 100% of Rekordbox writes are preceded by a verified Backup and
  followed by readback verification; zero unrecovered library incidents over
  the project.
- **SC-007**: Every review action (navigate, accept, reject, preview) is
  performable without a pointing device, verified for 100% of Review Queue
  items in testing.
- **SC-008**: At least 80% of Collection Tracks carry at least one Enriched
  Genre after enrichment, and the DJ judges at least 90% of a 50-track sample
  usable for booking filtering.
- **SC-009**: Preparing the playlist side of a booking (match, review, apply,
  structure fill) takes under 30 minutes where it took hours, judged by the DJ
  on the first real booking prepared with the app.
- **SC-010**: A playlist created or updated by Apply is visible and intact in
  Rekordbox after a Rekordbox restart, for 100% of applies in testing.

## Out of Scope (v1)

- Cloud or multi-user deployment of any kind; the app serves one operator on
  one machine.
- Downloading or ripping audio from Spotify, Apple Music or anywhere else;
  store deep links are the only acquisition path.
- Editing Rekordbox track metadata, cues or beat grids.
- Waveform rendering; playback ships with a basic progress bar.
- Native app packaging; the app runs in the browser against a local process.
- Structure templates (reusing a designed Booking Structure for the next
  booking); wanted, explicitly deferred to the parking lot.
- Automatic watching of Spotify playlists for changes; a re-sync is always
  operator-initiated.
- Analytics mirroring to any external database.

## Assumptions

- The DJ owns a working Spotify Premium account, required for full-length
  in-app playback of Spotify originals; without Premium the review flow
  degrades to local preview only.
- The library is mp3/m4a without embedded ISRC tags, so fuzzy matching carries
  the product; the identifier fast lane is expected to hit near zero and gets
  no UI investment.
- Add-only semantics (never remove, never reorder) extend from Target Playlists
  to applied Booking Structures, per the same decision (ADR 0006); absence of a
  track in Rekordbox is never interpreted as DJ intent.
- The choice of external enrichment source(s) (Spotify artist genres and/or an
  open music database) is an architecture decision, contingent on the planned
  coverage spike; this spec fixes the behaviour (coverage target, manual
  override, app-side only), not the source.
- The 80% enrichment coverage and 90% sample-quality targets in SC-008 are
  working targets to be confirmed or revised by that spike with the DJ judging;
  revising them is a recorded decision, not a silent edit.
- Whether full-length Spotify playback works against a localhost app is
  confirmed by an early spike (phase 1 unknown #3); its fallback is local
  preview plus opening the track in Spotify's own client.
- The fixture copy of the Rekordbox database, the Spotify developer
  registration, and confirmation of the database key on the DJ's machine are
  owner-supplied inputs still owed before implementation starts (grilling D10).
- Structure templates ("save this structure as a template for the next
  booking") are explicitly deferred, recorded in the parking lot, not silently
  dropped.
- Bought tracks appear in the Collection because the DJ imports them into
  Rekordbox as usual; the companion only detects them at the next re-sync, it
  does not watch the filesystem.

## Compliance notes (risk_class: minimal)

- **AVG/GDPR**: The spec implies exactly one category of personal data: the
  operator's own Spotify authorisation (tokens and the account identity needed
  to hold a session). Basis, retention and processors are recorded in the PII
  inventory next to this spec (`pii-inventory.md`). No other person's data is
  collected or stored.
- **NIS2**: Single machine, localhost-only, single operator; incident readiness
  is the operator stopping the process and restoring the latest Backup, which
  the Apply flow makes visible (SC-006, FR-016).
- **WCAG 2.2 AA**: This project has a user interface; every user story above
  carries its own accessibility acceptance criteria, none are waived.
- **OWASP**: No authentication surface exists beyond the Spotify authorisation
  flow and localhost binding; the full checklist still runs in phase 7 against
  that reduced surface.
