# Spotify plays a Missing Track, and the store link points at the iTunes Store

Supersedes ADR 0021, on the owner's instruction after using the buy queue: playing
a track should just run through Spotify, and the store link should land on the
iTunes Store rather than on Apple Music.

ADR 0021 chose the store's own 30 second preview, reasoning that it is audibly the
exact product being bought. The owner values something else more, and it is their
call: the tracks came out of a Spotify playlist they were listening to, they have
Premium, and the review queue already plays full tracks through Spotify, so there
is no reason for the buy queue to be the one place that plays a clip from a
different source.

Two facts checked before the switch rather than assumed. Every Missing Track
carries the Spotify track id it came from, verified across all 180 rows in the
owner's own database, so the source is always available. And Spotify no longer
returns `preview_url` for this application at all, so the switch necessarily means
the Web Playback SDK and a full track rather than a clip: the same machinery the
review queue already uses, which is why the two must share one player instead of
each creating their own.

The store link gains `app=itunes`, which Apple's own partner documentation
describes as the parameter that sends a music link to the iTunes Store instead of
defaulting to Apple Music. Combined with the `itmss` scheme from FR-042, a Mac
opens the Store page for the track inside the app, which is where buying happens.

Consequence, accepted: playback in the buy queue now needs Premium and a working
SDK, where a store preview needed neither. The store preview stays in the code as
the fallback for when Spotify cannot play, because losing the ability to hear
anything would be worse than hearing the wrong master, and the price and link do
not depend on it either way.

Decided 2026-08-19, on the owner's instruction.
