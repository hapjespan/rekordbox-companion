# PII Inventory: Rekordbox Companion v1

**Feature**: `specs/001-companion-v1/spec.md` | **Created**: 2026-08-16 |
**risk_class**: minimal

The spec implies personal data of exactly one person: the operator (the DJ).
No data about any other person is collected, stored or derived. Per the phase 2
rule this inventory therefore stops being one line and records each element.

| # | Data element | Where it lives | Lawful basis | Retention | Processors |
|---|---|---|---|---|---|
| 1 | Spotify OAuth tokens (access + refresh) of the operator's own account | Local app database on the operator's machine | Consent, given by the operator through Spotify's own authorisation flow | Until the operator disconnects the account in the app or revokes access at Spotify; deleted on disconnect | Spotify (the authorisation and API provider the operator already contracted with) |
| 2 | Spotify account identity needed to hold the session (account id, display name, Premium status) | Local app database on the operator's machine | Consent, same authorisation flow | Same lifetime as the tokens; deleted on disconnect | Spotify |
| 3 | Rekordbox library data (tracks, playlists, play counts) and its backups | The operator's own machine, where it already lives | Not personal data of a third party; the operator's own working data, processed locally at their instruction | Backups rotate automatically: zip-compressed, newest 10 kept (ADR 0016); the operator can delete them earlier by hand | None; never transmitted |

Explicitly not collected: listening behaviour beyond what Rekordbox already
stores, contact data, location data, data of guests or audiences, analytics or
telemetry of any kind. Search terms sent to the store-link lookup are track
metadata (artist, title), not personal data.

A change that adds a personal data element updates this inventory in the same
commit (constitution, AVG/GDPR article).
