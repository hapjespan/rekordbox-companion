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

## Architecture decisions

Every ADR in `docs/adr/`, in order. A superseded one names its replacement;
read that instead of citing the superseded text.

- [0001](adr/0001-local-first-single-process.md) — local-first, single-process web app bound to 127.0.0.1
- [0002](adr/0002-rekordbox-pin-7-2-17.md) — Rekordbox version pinned at 7.2.17
- [0003](adr/0003-fuzzy-matching-primary.md) — fuzzy matching is the primary path, ISRC is opportunistic
- [0004](adr/0004-delivered-design-tokens-binding.md) — the delivered design token set is binding, Inter substitutes the proprietary font
- [0005](adr/0005-rekordbox-history-ignored.md) — Rekordbox play history is ignored entirely
- [0006](adr/0006-add-only-playlist-updates.md) — companion-created playlists are updated add-only
- [0007](adr/0007-genre-enrichment-app-side.md) — genres are enriched from external sources and live only in the companion
- [0008](adr/0008-structures-hand-designed-with-suggestions.md) — Booking Structures are hand-designed by the DJ, the app only suggests tracks
- [0009](adr/0009-embedded-spotify-playback.md) — embedded Spotify playback in the review UI via the Web Playback SDK
- [0010](adr/0010-backups-never-pruned.md) — **superseded by 0016**: backups kept forever, no rotation
- [0011](adr/0011-free-tier-external-services.md) — external services are free-tier only
- [0012](adr/0012-in-memory-collection-index.md) — one in-memory collection index serves matching, search and suggestions
- [0013](adr/0013-genre-source-seam-incremental-runs.md) — genre enrichment: GenreSource seam, incremental resumable runs
- [0014](adr/0014-sse-for-progress.md) — progress streaming via Server-Sent Events
- [0015](adr/0015-openapi-client-generation.md) — frontend client generated from the OpenAPI export
- [0016](adr/0016-backup-rotation-keep-10-zipped.md) — backups are zip-compressed and rotate, keeping the newest 10
- [0017](adr/0017-write-spike-imports-pyrekordbox-directly.md) — the R3 write spike, and two verification tests, import pyrekordbox directly outside `rb/`
- [0018](adr/0018-musicbrainz-tags-primary-genre-source.md) — MusicBrainz artist tags, not Spotify genres, are the primary Enriched Genre source
- [0019](adr/0019-remix-veto-only-demotes.md) — the remix/edit veto only demotes, never promotes
- [0020](adr/0020-token-scale-extended-to-the-delivered-prototype.md) — the type scale is extended to the sizes the delivered prototype actually uses
- [0021](adr/0021-buy-decision-previews-come-from-the-store.md) — **superseded by 0022**: a Missing Track previewed from the store, not Spotify
- [0022](adr/0022-spotify-plays-the-buy-queue.md) — Spotify plays a Missing Track, and the store link points at the iTunes Store

## Deployment

`deploy_target: none` (`specs/PROFILE.md`), deliberately, not by omission: this is
a local-first single-DJ tool per ADR 0001, installed and run on the DJ's own Mac
against their own encrypted Rekordbox database, which no server should have
access to. Centrally hosting it would contradict the architecture the whole
project rests on. That stops being true only if a future version drops the
local-database read entirely in favour of a hosted data model, which is not
this project.

## Validation log

**Phase 7 review** (2026-08-18): the two-axis review, the ten OWASP verdicts,
the WCAG conformance statement with its three recorded deviations, the
reconciled PII inventory and the scope validation all live in
`specs/001-companion-v1/review-phase-7.md`. Thirteen blocking findings were
found and fixed across two revisions of the phase; what was recorded rather than fixed is
carried in `specs/001-companion-v1/backlog-post-v1.md`. Three success criteria
stay unproven because they need the owner rather than code: SC-002 and SC-003
(the Golden Set holds four illustrative stubs, not 50 real cases, T094) and
SC-009 below.

**SC-009** (booking-prep time under 30 minutes, where it took hours): a
manual sign-off, not a code deliverable (T103, gate-review finding: SC-009
had no recorded validation step). Not yet recorded -- pending the owner
preparing a real booking with the app and judging the actual time against
the pre-companion baseline. Nothing to log here until that first real
booking happens.
