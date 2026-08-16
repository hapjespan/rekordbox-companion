# Backups are kept forever; the app never deletes one

Every write to the Rekordbox database is preceded by a timestamped full backup,
and the companion never deletes any of them: no rotation, no age limit, no cap.
Disk usage is unbounded and explicitly accepted; cleanup is a manual act by the
owner. Considered alternatives: keep-last-N with a minimum age (rejected by the
owner: a pruned backup cannot be un-pruned, disk is cheaper than the library),
time-based expiry (rejected for the same reason). This closes off any automatic
backup-pruning design in the write path; the only backup logic that may exist
is create-and-verify. Decided in phase 3 grilling, 2026-08-16.
