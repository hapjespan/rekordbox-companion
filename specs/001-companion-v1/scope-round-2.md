# Scope round 2: three features the delivered design asks for

The owner reviewed the delivered design against the built app and put three of its
features back on the table, knowing it reopens phases 2 and 4: **XML export**,
**per-store checkout with purchase tracking**, and **a watch folder that imports
what was bought**. This file is the entry point for that round. It is not a
decision record and not a plan; it states what each feature collides with and the
questions that have to be answered before anything is specified, so the round
starts from the real conflicts rather than from the mockup.

Nothing here is implemented. The design work the owner approved in the same pass
(the sidebar with both playlist sources, musical key and label from Rekordbox, the
BPM curve, the buy queue's store card and summary, the match report's groups and
filters, and the builder's phase columns and checks) is ordinary phase 6 work and
proceeds separately.

## Why this reopens phases 2 and 4

Each of the three needs requirements that do not exist and data or behaviour the
architecture does not have. Two of them contradict a ratified decision rather than
merely extending it, and one moves files around inside the DJ's library, which is
the one thing this project has been most careful about. That is a specification
question, not an implementation detail, and the workflow's own rule applies:
uncertainty that surfaces while implementing means the specification was
insufficient, so the answer is to stop, grill, update the spec, and resume.

Consequence the owner accepted: gate 7 is no longer the next step. Phase 7's
review describes the app as it stands, and it cannot sign off features that are
not yet specified.

## 1. XML export

**Collides with ADR 0006 and the whole of US3.** The companion writes to
`master.db` add-only, behind `guard.check()` and a verified `backup.create()`, and
verifies by readback. An XML export is a second route into Rekordbox that none of
that protects: the DJ imports the file themselves, Rekordbox decides what it means,
and neither the guard, the backup nor the readback is in the path. SC-006's claim
that 100% of writes are preceded by a verified backup stops being true of the
system as a whole, even though it stays true of the code we control.

Questions the round has to answer:

- What does the export exist for that the guarded write does not already do? The
  design lists it beside "Naar Rekordbox sturen", so the two overlap.
- Is it an export of a match report, of a structure, or of the whole collection?
  Each is a different artifact with a different risk.
- Does SC-006 get reworded, or does the export carry its own guarantee, or is the
  export explicitly outside the safety claim and said so in the UI?
- Rekordbox XML is a documented format, but does 7.2.17 import it in a way that
  cannot duplicate or displace existing playlists?

## 2. Per-store checkout and purchase tracking

**Collides with FR-020 to FR-023.** Those settle on exactly one Store Link per
Missing Track, to the Apple Music / iTunes NL storefront, with a manual override
and three states: open, acquired, ignored. The design instead groups the queue by
store, totals per store, and hands the DJ off store by store while tracking what
has been paid for.

Questions:

- Which stores? The design names Beatport, Bandcamp, Traxsource and Discogs. Each
  is its own lookup, its own matching problem and its own terms; ADR 0011 caps the
  project at free-tier services, and none of those four has a free catalogue API
  comparable to the iTunes Search API.
- What does "afgerekend" mean without a purchase API? No store tells us the DJ
  paid. Either the DJ marks it, which is FR-021's `acquired` under a new name, or
  the app infers it from a file appearing, which is feature 3.
- Is a total across stores meaningful when the same track is sold in several, at
  different prices and qualities?
- The design shows format and quality per row (WAV 24-bit, FLAC, AIFF). Where does
  that come from before purchase?

## 3. Watch folder that imports purchases

**New behaviour with a risk profile of its own.** The design's after-purchase card
promises files land in `~/Music/Rekordbox Inbox`, get analysed for BPM and key, and
are added to the playlist. That is the app moving and writing files inside the DJ's
music library and triggering Rekordbox analysis, which is a categorically larger
permission than anything the app has today: until now it reads the library and
appends playlist rows behind a backup.

Questions:

- Does the app move files, or only watch and report? Watching and reporting is a
  fraction of the risk and most of the value.
- Who analyses? The app cannot make Rekordbox analyse; Rekordbox does that on
  import. So does this wait for the DJ to import, and then notice?
- What happens on a partial download, a duplicate, or a file that is not the track
  it claims to be?
- What is the failure mode when the folder is a network volume, or is full, or the
  DJ moves the file mid-write?
- Does anything here need a backup of its own, given that it writes outside
  `master.db` and therefore outside `rb/backup.py`'s remit?

## Suggested order

Answer feature 2 before feature 3: whether the app tracks purchases at all decides
whether a watch folder has a job. Feature 1 is independent of both and is the one
where a clear owner answer to "what is it for" may well end the discussion.
