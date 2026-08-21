# A Missing Track is previewed from the store, not from Spotify

**Status: superseded by ADR 0022** (2026-08-19, later the same day): the owner used the buy queue and asked for Spotify playback instead, on the reasoning that the tracks came from a Spotify playlist they already had Premium for. Kept for the record; do not cite.

FR-041 needs a Missing Track audible before the DJ buys it. Two sources could
serve that, and the store's own preview wins.

The store preview arrives in the iTunes Search response the app already makes to
find the Store Link, as a 30 second MP3 the browser plays directly. It costs no
new service, no credential and no new outbound host on the backend, and it is
audibly the same master the Store Link sells: previewing the exact product being
bought is the point of the preview.

The alternative was the Spotify Web Playback SDK, which is already wired for the
Review Queue and which the owner's Premium account supports. Rejected for this
purpose. It plays Spotify's copy, which for edits, remasters and remixes can be a
different master from the one the store sells, so it would answer a question the
DJ is not asking. It also needs a live player token and a Premium session for
something that must keep working while the DJ is offline from Spotify, and
Spotify's own `preview_url` is increasingly absent for newer applications, so the
cheap half of that route is closing anyway.

Consequence, accepted: a Missing Track with no store preview cannot be heard at
all in the app, and the queue says so rather than offering a dead control. The
Review Queue keeps using Spotify, because there the question genuinely is whether
the Spotify track and the Collection track are the same recording.

Decided 2026-08-19, on the owner's request after first real use.
