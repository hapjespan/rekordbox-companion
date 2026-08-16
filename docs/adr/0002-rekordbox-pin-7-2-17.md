# Rekordbox version pinned at 7.2.17

Rekordbox's database schema and encryption change between releases, and since
6.6.5 the decryption key is no longer extractable from a local install. The
project pins Rekordbox at 7.2.17 with auto-update disabled for the project
duration; the health check warns on mismatch. Upgrading Rekordbox is a
deliberate, gated action: check pyrekordbox release notes, back up, upgrade,
re-verify. Decided at kickoff (D1), 2026-08-16.
