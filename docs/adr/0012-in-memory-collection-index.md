# One in-memory collection index serves matching, search and suggestions

The collection (30.000+ tracks, tested at 40.000) is read from `master.db`
into one in-memory index behind the `rb` seam, rebuilt on demand and cached in
the process; matching, collection search and booking suggestions all consume
it. Considered alternatives: mirroring the collection into `app.sqlite` with
FTS5 (rejected: creates a second copy of Rekordbox data with a staleness
protocol, against kickoff §7's reference-don't-duplicate rule), querying
`master.db` per keystroke (rejected: couples UI latency to SQLCipher open cost
and Rekordbox file locks). Forty thousand short-string rows are a few tens of
MB in a single process (ADR 0001), and rapidfuzz over that list clears the
30s/100-track and 100ms-search budgets with margin. Decided in phase 4,
2026-08-16 (research R6).
