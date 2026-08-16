# PII Inventory: Rekordbox Companion v1

Maintained as required by the AVG/GDPR article at `risk_class: minimal`; more
than one line because the spec does imply personal data. All data belongs to
the single operator; no other person's data is collected. Source spec:
`specs/001-companion-v1/spec.md`.

| Element | Where | Lawful basis | Retention | Processors |
|---|---|---|---|---|
| Spotify OAuth tokens | Local machine only | Consent (owner connects their own account) | Until disconnect, which deletes them (FR-030) | Spotify (authentication endpoints) |
| Spotify account id and playlist contents | Local machine only | Consent, same flow | Until the owner deletes the app's data | Spotify (playlist endpoints) |
| Listening/library data (Collection, Play Counts) | Local machine only, read from the owner's own Rekordbox | Owner's own data, processed at their instruction | Lives in Rekordbox; companion copies are deletable | None |
| Store lookup terms (artist, title) | Sent as search terms | Legitimate interest of the owner (finding their own purchases) | Not retained beyond the stored Store Links | Apple (iTunes Search) |

No analytics, no telemetry, no third-party storage. A change that adds any
personal data element MUST extend this table in the same change (constitution,
AVG/GDPR article).
