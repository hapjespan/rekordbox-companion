# Data Model: Rekordbox Companion v1

Phase 1 output of `/speckit-plan`, 2026-08-16. Companion-owned data lives in
`data/app.sqlite` (SQLAlchemy 2.x models, Alembic migrations). Rekordbox data
is never duplicated wholesale: `rb_content_id` and `rb_playlist_id` reference
`master.db`; the in-memory collection index (research R6) is a cache, not a
store. Glossary terms per `docs/CONTEXT.md`.

## Tables

### spotify_auth (single row)

The operator's Spotify session. PII: see `pii-inventory.md`; deleted whole on
disconnect.

| column | type | notes |
|---|---|---|
| id | int PK | always 1 |
| access_token, refresh_token | text | never logged (constraints: NIS2) |
| token_expires_at | datetime | |
| account_id, display_name | text | identity needed to hold the session |
| product | text | `premium` gates embedded playback (ADR 0009) |

### playlist_link

The Target Playlist lineage (FR-010, FR-019, ADR 0006): one row per Spotify
playlist URL ever applied.

| column | type | notes |
|---|---|---|
| id | int PK | |
| spotify_playlist_id | text UNIQUE | parsed from the URL, never the raw URL |
| rb_playlist_id | text NULL | Rekordbox id of the Target Playlist; NULL until first Apply |
| rb_playlist_name | text | last name written |
| created_at, last_applied_at | datetime | |

### sync_session

| column | type | notes |
|---|---|---|
| id | int PK | |
| playlist_link_id | int FK | lineage; re-sync = new session, same link |
| spotify_snapshot_id | text | Spotify's playlist version marker |
| name | text | playlist name at fetch time |
| status | enum | `fetching` → `matching` → `ready` → `applied`; `failed` from any; a write whose readback verification fails does NOT transition to `applied` — it stays `ready` and the failure is reported with the `write_log` row's backup_path so the DJ knows which Backup to restore (spec.md US3 scenario 7) |
| created_at | datetime | |

### sync_track

One row per playlist position (duplicates in the playlist stay visible;
Apply de-duplicates, spec edge case).

| column | type | notes |
|---|---|---|
| id | int PK | |
| sync_session_id | int FK | |
| position | int | playlist order |
| spotify_track_id, isrc | text NULL | NULL for local/unavailable tracks |
| artist, title | text | as fetched |
| duration_ms | int | |
| status | enum | `matched`, `review`, `missing`, `rejected`, `unmatchable` |
| rb_content_id | text NULL | set when matched/accepted |
| match_score | real NULL | |
| candidates | json | top 3 `{rb_content_id, score, reason}` for review items |
| matched_at | datetime NULL | |

Status transitions: `review → matched` (accept), `review → rejected` (reject;
spawns missing_track), `missing → matched` (auto, on re-sync per FR-023).
`unmatchable` is terminal (no identifiers, spec edge case). `matched` never
transitions away. Accept/reject (T037) only ever apply to a track currently
`review`; attempting either from any other status is refused (409
`not_in_review`), not silently ignored or re-applied -- only `review` has an
accept/reject transition listed above at all (T036 build finding).

### missing_track

| column | type | notes |
|---|---|---|
| id | int PK | |
| sync_track_id | int FK UNIQUE | |
| itunes_track_id | text NULL | |
| itunes_url_auto | text NULL | best-effort pick (FR-022 keeps it) |
| itunes_url_chosen | text NULL | manual override wins when set |
| itunes_preview_url | text NULL | the automatic pick's 30s store preview (FR-041, ADR 0021) |
| itunes_price | real NULL | single-track price of the automatic pick; NULL when the store sells it album-only or streaming-only |
| itunes_currency | text NULL | ISO code, only ever set alongside a price |
| status | enum | `open` → `acquired` / `ignored`; `open → closed` via FR-023 auto-match |
| resolved_at | datetime NULL | |

`ignored` is sticky across re-syncs of the same playlist (spec US4 scenario 3).

### enriched_genre

| column | type | notes |
|---|---|---|
| id | int PK | |
| rb_content_id | text | index; multiple genres per track allowed |
| genre | text | normalised lowercase tag |
| source | enum | `spotify`, `musicbrainz`, `manual` |
| updated_at | datetime | |

Rule (FR-028): if any `manual` row exists for an `rb_content_id`, enrichment
runs never insert, update or delete rows for that track.

### enrichment_state

Per-track queue state that makes runs incremental and resumable (R1, ADR 0013).

| column | type | notes |
|---|---|---|
| rb_content_id | text PK | |
| status | enum | `pending`, `done`, `none_found`, `failed` |
| attempted_at | datetime NULL | |
| last_source | text NULL | |

`none_found` feeds the manual work list (FR-029). `failed` is retryable.

### booking_profile / booking_profile_genre_tag

| column | type | notes |
|---|---|---|
| id | int PK | |
| name, slug | text UNIQUE | seeded: horeca, bruiloft, prive, thema (FR-031) |
| bpm_min, bpm_max | int NULL | optional range |

`booking_profile_genre_tag(profile_id FK, tag text)` — many per profile.

### structure / structure_node / structure_track / suggestion_dismissal

| table | columns | notes |
|---|---|---|
| structure | id PK, name, booking_profile_id FK NULL, created_at, last_applied_at NULL | one per designed Booking Structure |
| structure_node | id PK, structure_id FK, parent_id FK NULL, kind enum(`folder`,`playlist`), name, position, set_phase text NULL, rb_ref text NULL | the tree; `rb_ref` set after Apply so re-apply is add-only (FR-018); set_phase is a label (vooravond/mid/prime/sluit), not logic |
| structure_track | node_id FK, rb_content_id, position, origin enum(`suggestion`,`manual`) | contents of playlist nodes |
| suggestion_dismissal | node_id FK, rb_content_id | dismissed Suggestions never return for that playlist (FR-034) |

### write_log

Audit trail for the guarded write path (constraints: NIS2 logging; SC-006).

| column | type | notes |
|---|---|---|
| id | int PK | |
| kind | enum | `sync_apply`, `structure_apply` |
| subject_id | int | session or structure id |
| backup_path | text | the Backup taken for this write (ADR 0016: may be pruned by rotation later; the log row remains) |
| readback_ok | bool | |
| detail | json | counts written, ids created |
| created_at | datetime | |

### app_config

`key text PK, value text` — paths, pinned Rekordbox version, auto-match bar
overrides if ever needed.

## Derived/in-memory (not persisted)

- **Collection index** (R6/ADR 0012): list of `{rb_content_id, artist, title,
  norm_artist, norm_title, remix_tokens, duration_ms, bpm, isrc, play_count,
  location}` rebuilt from `master.db` on demand; serves matching, search and
  suggestions.
- **Suggestions** are computed, never stored: filter index by profile tags
  (against enriched_genre) and BPM, rank by play count, subtract current
  `structure_track` rows and `suggestion_dismissal` rows.
- **Matching engine seam** (FR-004..FR-009; T019 review finding, corrected by
  T020/T021 review): pinned here once so US1's test tasks (T019-T023) and
  implementation tasks (T024-T025) agree on it independently, instead of
  each test file deciding it implicitly.
  `classify_match(spotify: dict, collection: dict) -> MatchResult`:
  - `spotify`: `{artist, title, duration_ms, isrc?}` — raw, as fetched for one
    Sync Session track (at most 999 per playlist, D12); `classify_match`
    normalises it internally, which is cheap once per track.
  - `collection`: `{norm_artist, norm_title, remix_tokens, duration_ms,
    isrc?}` — the PRECOMPUTED fields of a Collection index entry (see
    above), never raw `artist`/`title`. `classify_match` is the hot loop
    scoring one Spotify track against many Collection entries (up to ~40k,
    phase-3 grilling) to find the top-3 fuzzy candidates, so re-normalising
    the collection side per comparison would cost O(tracks x collection)
    regex work instead of the O(collection) ADR 0012's precomputation
    already pays for once at index-build time. A caller assembling a
    `collection` dict from anything other than an `IndexEntry` (the golden
    fixture's human-authored plain `artist`/`title`, T019) must run it
    through `normalize()`/`extract_remix_tokens()` itself first — see
    `test_matching_golden.py`'s `_collection_dict` helper.
  - `MatchResult` exposes `.status` (`"matched" | "review" | "missing"`, per
    FR-005..FR-008's tiers) and `.score` (0-100, FR-006/FR-007's fuzzy weight).
  Plain dicts over typed dataclasses: the caller (sync flow) already holds
  both shapes as dicts (Spotify API JSON, collection index entries above), so
  a dataclass would just add a conversion step with no consumer that needs
  it yet — the "boring" choice per project conventions.

## Validation rules

- `spotify_playlist_id` is extracted server-side from the pasted URL; raw URLs
  are never stored or fetched (constraints: ASVS V5).
- Genre tags normalise to lowercase, trimmed, deduplicated on write.
- `bpm_min <= bpm_max` when both set.
- Structure names and playlist names: non-empty, ≤120 chars, validated with
  field-naming errors (WCAG criteria in every story).
- One `missing_track` per `sync_track` (UNIQUE), one `playlist_link` per
  Spotify playlist id (UNIQUE).
