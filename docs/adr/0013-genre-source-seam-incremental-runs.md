# Genre enrichment: GenreSource seam, incremental resumable runs

**Source ordering superseded by ADR 0018** (phase 6, 2026-08-18): the T066
coverage spike found Spotify artist genres unavailable to this app in
practice. The `GenreSource` seam and incremental/resumable run design below
are unchanged and still current.

Enrichment lives behind one `GenreSource` interface with two designed
adapters: Spotify artist genres (primary; session already authorized) and
MusicBrainz genre tags (secondary; open data, 1 request/second). Runs are
incremental and resumable via per-track queue state, never one bulk pass,
because 30.000+ tracks against free-tier rate limits (ADR 0011) is a
multi-hour, interruptible job. Manual overrides are not a source: they live in
the app database and any track with one is skipped by every run (FR-028).
Considered alternatives: Last.fm tags (rejected as primary: folksonomy noise,
kept as reserve adapter), Discogs (rejected: strict rate limits plus OAuth for
quota), paid providers (killed by ADR 0011), bulk one-shot enrichment
(rejected: cannot survive interruption at this scale). The coverage spike
(research R1) decides whether the MusicBrainz adapter ships in v1 or stays a
stub behind the seam. Decided in phase 4, 2026-08-16.
