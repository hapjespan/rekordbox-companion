# External services are free-tier only

The companion may only depend on external services that are usable without
payment: the Spotify Web API as a personal app in developer mode, the iTunes
Search API, and a genre-enrichment source with a free tier (for example an open
music database). Considered alternative: paid music-data APIs for enrichment
coverage (rejected by the owner: budget is own time plus free tiers, no paid
services). This closes off paid enrichment sources in the phase 4 source
decision and caps design assumptions at free-tier rate limits, which matters at
a 20.000+ track collection: enrichment must be designed to run incrementally
and resumably within those limits rather than as one bulk pass. Decided in
phase 3 grilling, 2026-08-16.
