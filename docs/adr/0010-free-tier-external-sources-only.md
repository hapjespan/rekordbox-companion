# External sources must be free of recurring cost

Every external source the companion consumes — genre enrichment, store-link
lookup, anything phase 4 adds — must run on a free API tier: the budget for
recurring cost is €0 beyond the owner's existing Spotify Premium. This closes
off paid enrichment providers and paid lookup APIs as design options, and makes
rate limits a design input rather than something money can lift: the
enrichment time budget (full run ≤ 12 hours, resumable; constraint C-09)
exists because free tiers are throttled. Candidate sources that fit: Spotify
artist genres (already authorised), MusicBrainz, Discogs' free tier, the
iTunes Search API. Decided in phase 3 grilling (D14), 2026-08-16.
