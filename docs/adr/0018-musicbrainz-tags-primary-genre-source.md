# MusicBrainz artist tags (not Spotify genres) are the primary Enriched Genre source

Supersedes ADR 0013's source ordering (Spotify artist genres primary,
MusicBrainz secondary). The T066 coverage spike found Spotify's artist
`genres` field unavailable to this app in practice, verified with three live
calls against the real Spotify Web API: `GET /v1/search?type=artist` returns
artist objects with no `genres` key at all, `GET /v1/artists/{id}` returns 200
but omits `genres` (and `followers`/`popularity`) entirely, and
`GET /v1/artists?ids=...` (batch) returns 403 Forbidden outright. This matches
Spotify's November 2024 policy change restricting several artist-metadata
fields for apps in Development Mode without an approved extended-quota
request — not a bug in this integration, and not something this app can route
around without a request to Spotify with an unknown approval timeline.

MusicBrainz's own curated `genres` field (`inc=genres`) is not a viable
replacement as specced either: it is frequently empty even for prominent
artists (verified live: Daft Punk returns zero curated genres). Its
community `tags` field (`inc=tags`), however, carries real and relevant
signal for dance/electronic genres at exactly the coarse grain Booking
Profile filtering needs (verified live: Daft Punk's tags include
`electronic` ×40, `house` ×20, `french house` ×18, `disco` ×4, alongside
noisier low-count entries) — a different field, and a different filtering
job (rank by count, take the top N above a minimum threshold), than ADR
0013's "MusicBrainz genre tags" framing assumed.

**Decision**: `musicbrainz.py` becomes the sole adapter behind the
`GenreSource` seam (ADR 0013's seam design is unchanged), reading `inc=tags`
and ranking by count rather than reading `inc=genres`. The Spotify-genres
adapter is dropped, not stubbed: there is no code path that would make it
start working without an external, uncontrollable approval from Spotify.
Last.fm remains the reserve adapter behind the same seam if MusicBrainz's
measured coverage falls short of SC-008 on the owner's real collection.

Rate limit (1 req/s, ADR 0013) and incremental/resumable runs are unchanged.
The fixture `master.db` used to verify the above is Rekordbox's own ~119-track
demo library, not the owner's real collection, so the coverage percentage
itself (SC-008's ≥80%/≥90% thresholds) is still to be measured for real on the
owner's Mac against the full library, per the project's established pattern
for anything needing the real install (research.md R3 precedent).

Decided in phase 6 implementation (T066), 2026-08-18.
