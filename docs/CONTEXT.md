# Rekordbox Companion

A working DJ receives song requests and reference lists as Spotify playlists, but
performs from a personal, carefully curated local music library managed in
Rekordbox. Today there is no fast way to know which requested tracks the library
already holds, to turn that knowledge into a performance-ready playlist, to see
what is missing and buy it, or to slice the library into structures that fit a
booking. Preparing a single booking costs hours of manual cross-checking. This
project exists to collapse that preparation time while never putting the library
itself at risk.

## Language

### Library

**Collection**:
The DJ's complete Rekordbox library of tracks, read from Rekordbox's own database.
_Avoid_: library, catalog

**Collection Track**:
A single track in the Collection, identified by its Rekordbox content id.
_Avoid_: local track, file

**Play Count**:
The lifetime number of times a Collection Track was played in Rekordbox. A single
total with no per-event or per-context detail; it ranks tracks, it cannot split
them by occasion.
_Avoid_: play history, statistics

**Enriched Genre**:
A genre assigned to a Collection Track by the companion itself, sourced from
external music data and manually correctable. Lives only inside the companion;
the genre field in Rekordbox is never written.
_Avoid_: tag (reserved for Booking Profile genre tags)

### Matching

**Sync Session**:
One run of fetching a Spotify playlist and matching every track in it against the
Collection. Re-running the same playlist later starts a new Sync Session that
updates the same target playlist.
_Avoid_: import, scan

**Spotify Track**:
A track as it appears in the fetched Spotify playlist, with artist, title,
duration and identifiers.

**Match**:
The pairing of one Spotify Track with one Collection Track, carrying a score.
A Match is automatic when the score clears the auto-match bar, otherwise it
waits in the Review Queue.
_Avoid_: hit, link

**Review Queue**:
The list of doubtful Matches a Sync Session could not decide, resolved by the DJ
with keyboard-only actions: accept, reject, listen to both versions.
_Avoid_: conflicts, pending list

**Candidate**:
One of the up to three Collection Tracks offered for a doubtful Match in the
Review Queue, each carrying its score. Accepting a Candidate turns it into the
Match; rejecting means none of them is the requested track.
_Avoid_: option, alternative

**Reject**:
The DJ's verdict that none of the offered Collection Tracks is the requested
track. A rejected track becomes a Missing Track. Rejecting never means "I do not
want this track"; that intent is expressed by ignoring the Missing Track.

**Missing Track**:
A Spotify Track with no accepted Match, queued for acquisition with a Store Link.
Its status is open, acquired or ignored.
_Avoid_: unmatched, gap

**Store Link**:
A deep link to the exact track page in the Apple Music / iTunes Store, Dutch
storefront, where a Missing Track can be bought.

**Golden Set**:
The fixed collection of real match cases with expected outcomes that every
change to matching behaviour is judged against. It may grow, it may never be
weakened.

### Writing to Rekordbox

**Target Playlist**:
The companion-created Rekordbox playlist that Applies of one Spotify playlist
URL write to. The same URL always maps to the same Target Playlist; if the DJ
deleted it inside Rekordbox, the next Apply recreates it and says so.
_Avoid_: destination, output playlist

**Apply**:
The single guarded action that writes a Sync Session's accepted Matches, or a
Booking Structure, into Rekordbox. Applying to an existing companion-created
playlist only ever adds tracks, it never removes or reorders them.
_Avoid_: export, sync back, push

**Guard**:
The precondition check that refuses any write to Rekordbox's database while
Rekordbox is running or when the pinned Rekordbox version does not match.

**Backup**:
The timestamped copy of Rekordbox's database taken before every write, without
exception.

### Bookings

**Booking Type**:
A kind of engagement the DJ plays: horeca, bruiloft, prive, thema.
_Avoid_: gig type, event type

**Booking Profile**:
The companion's description of one Booking Type: its genre tags and optional BPM
ranges, used to filter and rank Suggestions.

**Booking Structure**:
A tree of folders and playlists the DJ designs freely in the companion for a
booking or Booking Type, then Applies to Rekordbox. Its shape is the DJ's own:
typically genre or theme playlists split by Set Phase, plus a Run-of-Show folder.
_Avoid_: structure proposal, generated structure

**Set Phase**:
A named slot of the night that subdivides a Booking Structure: vooravond, mid,
prime, sluit.
_Avoid_: time slot, segment

**Run-of-Show**:
The folder inside a Booking Structure holding Moment Playlists, in Dutch: het
draaiboek.

**Moment Playlist**:
A playlist tied to one scripted moment of a booking, such as openingsdans,
proost, sluit.

**Suggestion**:
A Collection Track the companion proposes for one playlist in a Booking
Structure, ranked by Play Count and filtered by Enriched Genre and BPM. The DJ
curates Suggestions before anything is Applied.
_Avoid_: recommendation, auto-fill

## Validation log

**SC-009** (booking-prep time under 30 minutes, where it took hours): a
manual sign-off, not a code deliverable (T103, gate-review finding: SC-009
had no recorded validation step). Not yet recorded -- pending the owner
preparing a real booking with the app and judging the actual time against
the pre-companion baseline. Nothing to log here until that first real
booking happens.
