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
write path is confined to `rb/` per rule 1, no exception. Recorded as a phase 6
gate-review finding (T042 review), 2026-08-18.

**Widened in phase 8** (phase 7 review finding B3) to name a second, narrower
exception the original wording did not cover: `engine/tests/rb/test_writer_integration.py`
and `engine/tests/bookings/test_structure_apply.py` both import
`pyrekordbox.db6.database.Rekordbox6Database` directly, read-only, to verify what
`rb/writer.py` wrote by reading the fixture database back through a second, independent path -- checking the writer's output with something other than the writer, which is the point of an integration test and would be circular through `rb/reader.py`. This is test-side verification, never production code, and it opens the encrypted database read-only after a write the guarded path already made: it carries none of the risk rule 1 exists to bound. The rule itself is unchanged; these two files and the one spike file above are the only permitted exceptions.
