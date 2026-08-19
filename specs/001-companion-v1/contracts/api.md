# API Contract: Rekordbox Companion v1

Phase 1 output of `/speckit-plan`, 2026-08-16. This document is the design of
the HTTP interface; the executable schema of record is FastAPI's OpenAPI
export, and per project rule 4 every API change starts there, after which
`pnpm openapi` regenerates the TypeScript client. This contract reshapes
kickoff §8: the `structure_proposal` endpoints are gone (ADR 0008), replaced by
structures, suggestions and enrichment.

Conventions: JSON bodies; errors as `{code, message, field?}` where `field`
names the offending input (WCAG form-error criterion flows from here); all
endpoints bind to `127.0.0.1:8787`; UI copy is Dutch but `code` values are
stable English identifiers.

## Health and collection

| Method & path | Request | Response | Notes |
|---|---|---|---|
| GET `/api/health` | – | `{status, rekordbox_version, version_pin_ok, db_path, rekordbox_running, ffmpeg_ok}` | guard visibility (FR-015) |
| GET `/api/collection` | `?query=&ids=&sort=&limit=&offset=` | `{total, items: [CollectionTrack]}` | serves US5; 100ms budget (SC-005) |
| POST `/api/collection/reindex` | – | `{indexed_count, took_ms}` | rebuilds in-memory index (R6) |
| GET `/api/playlists` | – | `[PlaylistNode]` | read-only |
| GET `/api/playlists/{rb_playlist_id}/tracks` | `?query=&sort=&limit=&offset=` | `{total, items: [CollectionTrack]}` | the Collection view filtered to one Rekordbox playlist; same row shape as `/api/collection` so the client reuses one table |
| GET `/api/config` | – | `{key: value, ...}` | every row in `app_config` |
| PUT `/api/config` | `{key: value, ...}` | `{key: value, ...}` | upserts the given keys, echoes the *whole* table back (not just the changed keys) |

`CollectionTrack`: `{rb_content_id, artist, title, duration_ms, bpm,
play_count, genres: [{genre, source}], format, musical_key, label}` — genres
come from enrichment, never from Rekordbox's genre field. `musical_key` and
`label` are Rekordbox's own `KeyName`/`LabelName`, each independently `null`
(both are absent for most tracks in a partly analysed library, and never
assumed present). `musical_key` is verbatim as Rekordbox stores it: Camelot
notation like `8m`/`2d`, occasionally a classical spelling like `G m`, never
normalised or converted, because the DJ recognises their own notation and a
lossy conversion is worse than none. Named `musical_key`, not `key`, so a row
object never carries a field that reads as an identifier.

`?ids=` on `GET /api/collection` requests exact `rb_content_id`s (repeated,
`?ids=a&ids=b`), for a caller that already knows which tracks it wants (a
Structure node's phase rows, the review queue's candidate cards) and would
otherwise sweep every page to find them. It is a filter, applied before
`query`, `sort`, `limit` and `offset` -- the same position `query` already
occupies -- so a caller wanting every one of N ids back in one page sets
`limit >= N`. Bounded to the same 200 as `limit`, for the identical reason
(a phase 7 finding already caught the unbounded-`limit` version of this
defect): `422` with `code: too_many_ids`, `field: ids`. An id absent from the
collection is simply absent from the result, never an error.

`GET /api/playlists/{rb_playlist_id}/tracks` serves the same body from the
same in-memory index: only the playlist's membership comes from `master.db`
(that relation exists nowhere else), never a second per-request pass over the
whole collection. Its `sort` accepts the four `/api/collection` fields plus
`position`, Rekordbox's own playlist order, which is also the default since no
index field can reconstruct it. Errors: `503 rekordbox_not_found` (no
database, same as the other Rekordbox endpoints), `404
rekordbox_playlist_not_found` for an unknown id, `409 collection_not_indexed`
when no scan has run yet, because "scan first" and "this playlist is empty"
must not look the same. A playlist that exists and holds nothing is a normal
`{total: 0, items: []}`, and a member the index no longer knows (removed from
Rekordbox since the last scan) is skipped rather than rendered as an empty
row.

`PlaylistNode`: `{rb_playlist_id, name, parent_id, is_folder, position}` —
a flat list, not a nested tree; the client reconstructs hierarchy from
`parent_id` (T101 gate-review finding: this word was "tree" before,
the shape was always flat per `rb/reader.py`'s `read_playlist_tree`, T012).

## Spotify auth

| Method & path | Notes |
|---|---|
| GET `/api/auth/spotify/login` | starts PKCE flow, loopback redirect |
| GET `/api/auth/spotify/callback` | completes it |
| GET `/api/auth/spotify/status` | `{connected, display_name, product}` |
| POST `/api/auth/spotify/disconnect` | deletes `spotify_auth` row — the PII deletion path |
| GET `/api/auth/spotify/player-token` | short-lived token for the Web Playback SDK (R2) |

## Spotify playlists

| Method & path | Request | Response |
|---|---|---|
| GET `/api/spotify/playlists` | – | `[SpotifyPlaylist]`: the operator's own playlists, so a sync starts from a click instead of a pasted URL |

`SpotifyPlaylist`: `{spotify_playlist_id, name, image_url, owner_display_name,
sync}`. There is deliberately **no track count**: Spotify strips the `tracks`
object from `/me/playlists` items for this application, so any count would be
invented. `image_url` is the smallest of Spotify's three cover sizes still
sharp enough for a sidebar thumbnail (>= 160px, falling back to the widest
known size, `null` for a playlist without cover art); `owner_display_name` is
`null` when Spotify gives none. The whole account is gathered by paginating
Spotify's own `next` cursor (101 playlists for the owner's account).

A Spotify refusal is never an empty list (phase 7 finding): `409
spotify_not_connected`, `409 spotify_session_expired`, `503
spotify_not_configured`, and `502 spotify_playlists_unavailable` for any other
refusal (403/429/5xx): Spotify answered, and the answer was "no".

`SpotifyPlaylist.sync` is the app's OWN status, derived from `playlist_link`
and the latest `sync_session` of that link, never from Spotify:
`{state, session_id, session_created_at, last_applied_at, totals}`. `state` is
`not_scanned` when this app never synced the playlist, otherwise the latest
session's `sync_session.status` verbatim (`fetching`, `matching`, `ready`,
`applied`, `failed`). `totals` is the same
`{matched, review, missing, rejected, unmatchable}` map as `SyncSession.totals`
(all five keys always present), `null` while `not_scanned`. State and counts,
never a rendered sentence: the sidebar's "gematcht · 12 ontbreken" is Dutch UI
copy and belongs in the frontend.

## Sync sessions (US1-US3)

| Method & path | Request | Response |
|---|---|---|
| POST `/api/sync/sessions` | `{playlist_url}` | `SyncSession` (starts fetch+match; progress via SSE) |
| GET `/api/sync/sessions` | – | recent sessions with totals |
| GET `/api/sync/sessions/{id}` | – | `SyncSession` + `[SyncTrack]` incl. candidates |
| POST `/api/sync/sessions/{id}/tracks/{tid}/accept` | `{rb_content_id}` | updated `SyncTrack` |
| POST `/api/sync/sessions/{id}/tracks/{tid}/reject` | – | updated `SyncTrack` (spawns Missing Track) |
| POST `/api/sync/sessions/{id}/apply` | `{playlist_name?}` | `ApplyResult` |

`ApplyResult`: `{rb_playlist_id, created: bool, tracks_added, tracks_already_present,
backup_path, readback_ok}`. Refusals are `409` with `code` one of
`rekordbox_running`, `version_mismatch`, `backup_failed`,
`insufficient_disk`; the message names the fix (US3 scenarios 2-3, edge case
disk space).

`SyncSession.totals`: `{matched, review, missing, rejected, unmatchable}` —
exactly one status per track (FR-003).

## Missing tracks (US4)

| Method & path | Request | Response |
|---|---|---|
| GET `/api/missing` | `?status=open` | `[MissingTrack]` |
| POST `/api/missing/{id}/status` | `{status: acquired\|ignored\|open}` | updated row |
| POST `/api/missing/{id}/link` | `{itunes_url}` | manual override (FR-022) |
| POST `/api/missing/refresh-links` | – | re-runs iTunes lookups for open rows, at most 20 per call and throttled to the free-tier rate (ADR 0011); `{refreshed, skipped, remaining}`, so the caller can resume. A row that fails is skipped, never fatal: the links already fetched are kept (phase 7 finding: one failure rolled the whole batch back) |

`MissingTrack`: `{id, artist, title, status, itunes_url_auto,
itunes_url_chosen, effective_url, no_link_found: bool, itunes_preview_url,
itunes_price, itunes_currency}`. The last three are the automatic pick's own
store preview and price (FR-041, ADR 0021), filled by the same lookup that
resolves `itunes_url_auto` and each independently `null`: a track can have no
preview, and a streaming-only or album-only track has no single-track price
(iTunes signals that by omitting `trackPrice` or returning `-1.00`, both of
which become `null` here). The preview is played by the browser straight from
Apple's preview host, never proxied through the backend.

## Enrichment (US6)

| Method & path | Request | Response |
|---|---|---|
| POST `/api/enrichment/run` | – | `{queued}` — incremental, resumable (ADR 0013); progress via SSE. `409` with `code: enrichment_already_running` while a run is in flight, so a reload or a second tab cannot start a second run racing the first on the same database (phase 7 finding) |
| GET `/api/enrichment/status` | – | `{pending, done, none_found, failed, coverage_pct, running}`. `running` is what the UI derives its disabled state from, rather than local component state. `coverage_pct` counts distinct enriched tracks over the whole collection index, which is SC-008's own wording, not over queue rows (phase 7 finding) |
| GET `/api/enrichment/unenriched` | paging | the manual work list (FR-029) |
| PUT `/api/collection/{rb_content_id}/genres` | `{genres: [text]}` | manual override, wins forever (FR-028) |

## Profiles and structures (US7)

| Method & path | Request | Response |
|---|---|---|
| GET/POST `/api/profiles`; PUT/DELETE `/api/profiles/{id}` | name, bpm range, `genre_tags: [text]` | profile CRUD (FR-031); `422` with `code: duplicate_name`, `field: name` when the name or its derived slug is taken, on create and on rename alike (phase 7 finding: rename raised a bare 500) |
| GET/POST `/api/structures`; PUT/DELETE `/api/structures/{id}` | name, profile ref | structure CRUD |
| GET `/api/structures/{id}/nodes`; POST `/api/structures/{id}/nodes`; PUT/DELETE `/api/structures/{id}/nodes/{nid}` | kind, name, parent, position, set_phase | tree editing (FR-032); GET lists the structure's tree, ordered by position -- added during phase 6 build (T087/T088 finding), a client cannot render or edit a tree it can never fetch |
| GET `/api/structures/{id}/nodes/{nid}/suggestions` | `?limit=` | `[Suggestion]` filtered by profile, ranked by play count, flags `already_in_playlist` (FR-033) |
| PUT `/api/structures/{id}/nodes/{nid}` re-parenting | `parent_id` | `422` with `code: invalid_parent` when the parent is unknown or belongs to another structure, `code: parent_cycle` when it is the node itself or one of its descendants, both `field: parent_id`. Refused before anything is stored, so the cycle can never reach apply, where it used to surface as a 500 after a backup had already been made (phase 7 finding) |
| GET `/api/structures/{id}/nodes/{nid}/tracks` | `?limit=&offset=` | `{total, items: [CollectionTrack]}` | the node's stored `structure_track` rows in their stored `position` order -- unlike Suggestions above (profile-filtered, play-count-ranked), this is everything the node actually holds, same row shape as `GET /api/collection` |
| POST `/api/structures/{id}/nodes/{nid}/tracks` | `{rb_content_id, origin}` | accept into playlist |
| DELETE `/api/structures/{id}/nodes/{nid}/tracks/{rb_content_id}` | – | remove from (unapplied) playlist node |
| POST `/api/structures/{id}/nodes/{nid}/dismissals` | `{rb_content_id}` | dismiss suggestion (FR-034) |
| POST `/api/structures/{id}/apply` | – | `ApplyResult` variant with per-node results; same guard contract as sync apply (FR-035) |

## Player and events

| Method & path | Notes |
|---|---|
| GET `/api/player/stream/{rb_content_id}` | HTTP Range; transcode fallback; `404` with `code: file_missing` when the audio file is gone (FR-026); path always resolved from the id, never client-supplied (ASVS V6/V12) |
| GET `/api/events` | SSE: `sync_progress`, `enrichment_progress`, `apply_done` events (R4) |

## Contract test obligations

- Every endpoint above appears in the OpenAPI export with typed request and
  response models; the generated client compiles against it (rule 4).
- Refusal codes of the two apply endpoints are contract-tested (they encode
  the guard, Principle II).
- `/api/collection` is perf-tested at 40.000 index entries (constraints).
