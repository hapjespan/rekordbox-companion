# Runbook: incident detection and notification

Phase 8 deliverable, per the NIS2 plan recorded in `docs/constraints.md` and the
compliance article in `docs/process/workflow.md`. `risk_class: minimal` and
`deploy_target: none` (`specs/PROFILE.md`) scale what this document has to be:
a proportional one-operator plan, not an on-call rotation, because there is no
service to page anyone about.

## Who

**Martien** is the operator, the owner, and the only user. There is no second
person to notify, no team, no on-call rotation. Every "who is notified" answer
below is the same person who would detect the incident in the first place,
which is why detection and notification collapse into one step rather than two.

## What counts as an incident here

The three things this project's own risk analysis (`docs/constraints.md`,
`specs/001-companion-v1/pii-inventory.md`) names as worth reacting to:

1. **A Rekordbox write went wrong**: a backup that fails to verify, an Apply
   that reports `readback_ok: false`, or (found and fixed in phase 8, see
   `docs/adr/0016-backup-rotation-keep-10-zipped.md` and the write-ahead-log fix
   in `rb/backup.py`) a backup that turns out not to contain the database's
   full committed state.
2. **A credential leaked**: the Spotify OAuth tokens or the SQLCipher key
   appearing somewhere they should not (a log line, a committed file, a shared
   screen). `engine/src/companion/logging.py`'s redacting formatter is the
   structural defence; this is what happens if it is ever wrong.
3. **The Spotify or iTunes integration silently breaks**: this project has
   already lived through this once. Spotify's March 2026 API migration renamed
   `/playlists/{id}/tracks` to `/playlists/{id}/items` with no advance notice
   reaching this codebase, and the app kept running, just wrong: every sync
   quietly failed with a message that read like a permissions problem. See
   `engine/src/companion/integrations/spotify.py`'s module-level comments at
   the fetch functions for the exact history. An external API changing its
   contract without warning is a realistic recurring risk for this project
   specifically, not a hypothetical.

## Detection

There is no monitoring service, because there is no deployment to monitor
(`docs/CONTEXT.md`'s Deployment section). Detection is Martien noticing:

- The app's own UI surfacing a Dutch error message instead of the expected
  result — this project has a specific, hard-won discipline against silent
  failure (`specs/001-companion-v1/backlog-post-v1.md` documents four separate
  cases where a failure used to read as an empty result, all fixed), so a real
  failure should be visible on screen rather than hidden.
- The terminal running `make dev` or `make run`, where structured JSON log
  lines appear for every guard refusal, backup, write, and run summary
  (`docs/constraints.md`'s logging plan).
- `GET /api/health` reporting `status: degraded` or `version_pin_ok: false`.

## Notification

Self-directed and immediate: Martien sees it, Martien acts on it, in the same
sitting. The channel is whichever of the app's UI or its terminal surfaced the
problem. There is no window to notify within because there is no one else to
notify; the window that matters is not doing the next Rekordbox write until the
cause is understood, which the guard (`rb/guard.py`) already enforces
structurally for the "Rekordbox is running" and "wrong version" cases, and
which is a manual discipline for everything else.

## Response, per incident type

1. **A write or backup problem**: stop. Do not Apply again. The backup
   directory (path reported in the write's response and in the log line) holds
   the pre-write state; restore it by hand in Rekordbox before doing anything
   else. Then read `docs/adr/0016-backup-rotation-keep-10-zipped.md` and the
   write-ahead-log section of `rb/backup.py`'s docstring to understand whether
   the backup itself was sound.
2. **A credential leak**: revoke it at the source first — disconnect Spotify
   in the app (`POST /api/auth/spotify/disconnect`, which is also the AVG/GDPR
   deletion path, `docs/CONTEXT.md`), or re-run `pyrekordbox download-key` for
   the SQLCipher key on the Mac. Rotate before investigating how it leaked.
3. **An external API changed contract**: check `/api/health` and the sync
   error message first; both are designed to say what actually failed rather
   than degrade silently. Compare the failing endpoint's real response against
   what `engine/src/companion/integrations/spotify.py` or
   `engine/src/companion/integrations/itunes.py` expects. This has already
   happened once (the March 2026 rename); expect it to happen again, on a
   timescale outside anyone's control.

## What this runbook is not

Not an SLA, not an escalation ladder, not a paging policy. `deploy_target: none`
means there is no hosted service whose downtime affects anyone but the operator
at the moment they try to use it. If that ever changes — if this project is
ever deployed somewhere reachable by someone other than Martien — this runbook
stops being sufficient and needs the full incident plan `risk_class: standard`
would demand, per `docs/process/workflow.md`'s compliance article.
