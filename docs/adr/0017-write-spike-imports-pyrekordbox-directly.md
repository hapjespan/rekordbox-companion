# The R3 write spike imports pyrekordbox directly, outside `rb/`

Rule 1 (CLAUDE.md) is "never import pyrekordbox outside `engine/src/companion/rb/`."
`engine/tests/spikes/rb_write_smoke.py` (T042) imports
`pyrekordbox.db6.database.Rekordbox6Database` directly, in `engine/tests/`, not
`rb/`. This is a narrow, deliberate exception, not a precedent for production
code: the spike's entire purpose is characterizing pyrekordbox's raw write API
(`create_playlist`, `create_playlist_folder`, `add_to_playlist`, `commit()`)
*before* `rb/writer.py` (T048) exists to wrap it — a wrapper cannot precede the
thing it wraps. The read-path equivalent (`tests/rb/test_reader.py`) already
imports through `companion.rb.reader`, not raw pyrekordbox, because a read
wrapper already existed when that test was written; the write path had none
yet, which is exactly why this spike exists.

Once `rb/writer.py`, `rb/guard.py`, and `rb/backup.py` land, every *production*
write path is confined to `rb/` per rule 1, no exception. This ADR covers only
the one throwaway spike file that characterizes the API first. Recorded as a
phase 6 gate-review finding (T042 review), 2026-08-18.
