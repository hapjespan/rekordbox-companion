# Backups are zip-compressed and rotate, keeping the newest 10

Supersedes ADR 0010 (keep-all). Every write to the Rekordbox database is still
preceded by a timestamped full backup, but each backup is zip-compressed on
creation and only the newest 10 are kept. Pruning runs exclusively after a new
backup has been created and verified readable — never as a standalone
background job — so the set never shrinks below 10 verified restore points and
a failed backup can never trigger a prune. A backup that fails verification
blocks the write, the same as insufficient disk space. Zip over rar: rar is
proprietary and needs external tooling, zip is in the standard library.

The owner first chose keep-all (ADR 0010, grilling 21:13) and reversed to
keep-10-zipped in the same evening's second grilling round (21:33), confirmed
explicitly in reconciliation. Decided in phase 3 grilling (D13), 2026-08-16.
