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
| GET `/api/collection` | `?query=&sort=&limit=&offset=` | `{total, items: [CollectionTrack]}` | serves US5; 100ms budget (SC-005) |
| POST `/api/collection/reindex` | – | `{indexed_count, took_ms}` | rebuilds in-memory index (R6) |
| GET `/api/playlists` | – | Rekordbox playlist/folder tree | read-only |
| GET/PUT `/api/config` | key/values | same | paths, thresholds |

`CollectionTrack`: `{rb_content_id, artist, title, duration_ms, bpm,
play_count, genres: [{genre, source}], format}` — genres come from
enrichment, never from Rekordbox's genre field.

## Spotify auth

| Method & path | Notes |
|---|---|
| GET `/api/auth/spotify/login` | starts PKCE flow, loopback redirect |
| GET `/api/auth/spotify/callback` | completes it |
| GET `/api/auth/spotify/status` | `{connected, display_name, product}` |
| POST `/api/auth/spotify/disconnect` | deletes `spotify_auth` row — the PII deletion path |
| GET `/api/auth/spotify/player-token` | short-lived token for the Web Playback SDK (R2) |

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
| POST `/api/missing/refresh-links` | – | re-runs iTunes lookups for open rows |

`MissingTrack`: `{id, artist, title, status, itunes_url_auto,
itunes_url_chosen, effective_url, no_link_found: bool}`.

## Enrichment (US6)

| Method & path | Request | Response |
|---|---|---|
| POST `/api/enrichment/run` | – | `{queued}` — incremental, resumable (ADR 0013); progress via SSE |
| GET `/api/enrichment/status` | – | `{pending, done, none_found, failed, coverage_pct}` |
| GET `/api/enrichment/unenriched` | paging | the manual work list (FR-029) |
| PUT `/api/collection/{rb_content_id}/genres` | `{genres: [text]}` | manual override, wins forever (FR-028) |

## Profiles and structures (US7)

| Method & path | Request | Response |
|---|---|---|
| GET/POST `/api/profiles`; PUT/DELETE `/api/profiles/{id}` | name, bpm range, `genre_tags: [text]` | profile CRUD (FR-031) |
| GET/POST `/api/structures`; PUT/DELETE `/api/structures/{id}` | name, profile ref | structure CRUD |
| POST `/api/structures/{id}/nodes`; PUT/DELETE `/api/structures/{id}/nodes/{nid}` | kind, name, parent, position, set_phase | tree editing (FR-032) |
| GET `/api/structures/{id}/nodes/{nid}/suggestions` | `?limit=` | `[Suggestion]` filtered by profile, ranked by play count, flags `already_in_playlist` (FR-033) |
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
- `/api/collection` is perf-tested at 30.000 index entries (constraints).
