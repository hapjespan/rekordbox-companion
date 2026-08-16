# Genres are enriched from external sources and live only in the companion

The genre field in the Rekordbox library is messy and largely empty, so booking
features cannot build on it. The companion enriches genres per Collection Track
from external music data (Spotify and/or an open music database, source choice
is a phase 3/4 decision), stores them in its own database with manual override,
and never writes to Rekordbox's metadata: the read-only boundary for track
metadata (kickoff NG3) stands. Enrichment is a hard v1 dependency, because
Suggestions in Booking Structures filter on Enriched Genre. Decided in phase 1
grilling (D7), 2026-08-16.
