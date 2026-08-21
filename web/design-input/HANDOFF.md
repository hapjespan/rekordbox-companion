# Handoff: Crate Bridge — Rekordbox × Spotify Matcher

## Overview
Crate Bridge is a desktop-style tool that matches a Spotify playlist against a local
Rekordbox collection. It answers three questions for a DJ:

1. Which tracks of this Spotify playlist do I already own in Rekordbox?
2. Which ones are missing, and where can I buy them?
3. How do I arrange the resulting tracks into a set with a deliberate structure
   (energy curve, BPM progression, harmonic/Camelot key order)?

The design covers three views inside one application shell: **Match-overzicht**,
**Koop-wachtrij** (buy queue) and **Playlist builder**. UI language is Dutch.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes that show
intended look and behaviour. They are *not* production code to copy directly. The task is to
**recreate these designs in the target codebase's existing environment** (React, Vue, Electron,
SwiftUI, Tauri, etc.) using its established patterns, component library and state management.
If no environment exists yet, pick the most appropriate framework for a desktop-oriented tool
that must read local Rekordbox data and talk to the Spotify Web API, and implement the designs
there.

`Rekordbox Matcher.dc.html` is a single-file streaming prototype: markup plus a small logic
class holding demo data and view state. All styling is inline. Treat the inline styles as the
spec, not as the implementation style.

## Fidelity
**High-fidelity (hifi).** Colours, typography, spacing, radii and interaction affordances are
final and grounded in the attached Spotify-derived style reference (`DESIGN.md`). Recreate the
UI pixel-accurately with the codebase's existing primitives. All content is placeholder demo
data — replace it with real API/collection data.

## Screens / Views

### Shell (all views)
- Root: CSS grid, `grid-template-columns: 300px 1fr`, `grid-template-rows: 64px 1fr`,
  `height: 100vh`, `overflow: hidden`. Canvas `#000000`.
- Font family: Inter (substitute for SpotifyMixUI), weights 400/600/700.
- Designed at 1440×900; must survive down to ~900px wide (grids use `minmax(0, 1fr)`,
  pill buttons use `white-space: nowrap`).

**Top bar** — full width, row 1, height 64px, background `#000000`,
`border-bottom: 1px solid #1f1f1f`, padding `0 24px`, flex row, gap 16px, items centered.
- Logo lockup: 26×26 circle `#1ed760`, black "R" 13px/700; wordmark "Crate Bridge" 14px/700,
  `letter-spacing: -0.01em`. Lockup block is 252px wide (aligns with sidebar gutter).
- Search field: height 36px, background `#1f1f1f`, `border-radius: 500px`, padding `0 14px`,
  width 340px, gap 8px, text `#c5c5c5` 13px, magnifier glyph at 70% opacity,
  placeholder copy "Zoek in collectie of playlist".
- Spacer (`flex: 1`).
- Connection status, 12px `#b3b3b3`, gap 8px: 7px green dot `#1ed760`,
  "Rekordbox 6.8 verbonden", pipe divider `#333333`, "Spotify · djmarijn".
- Primary pill: height 32px, padding `0 16px`, `border-radius: 9999px`, background `#ffffff`,
  text `#000000` 13px/700, label "Sync". Hover background `#e6e6e6`.

**Sidebar** — column 1, background `#121212`, padding `20px 12px`, vertical scroll,
flex column, gap 24px.
- Section label style: 11px/700, `letter-spacing: 0.08em`, colour `#73777c`.
- Nav items ("WORKSPACE"): flex row space-between, padding `9px 12px`,
  `border-radius: 6px`, 13px/700. Inactive text `#b3b3b3` on transparent; active text
  `#ffffff` on `#292929`; hover background `#292929`. Trailing counter 11px:
  "Match-overzicht / 128", "Koop-wachtrij / <count>" (counter `#1ed760`, 700),
  "Playlist builder / 4 fases".
- "SPOTIFY PLAYLISTS" list rows: flex row, gap 12px, padding `8px 12px`,
  `border-radius: 6px`, hover `#1f1f1f`. 40×40 cover placeholder `#292929`, radius 6px,
  glyph ♫ `#535353`. Title 13px/600 with ellipsis; meta 11px `#b3b3b3`.
  Items: "Warehouse Winter 2026 / 128 tracks · gematcht", "Sunday Terrace / 64 tracks ·
  12 ontbreken", "Peak Time Weapons / 41 tracks · nieuw", "Discover Weekly / 30 tracks ·
  niet gescand".
- Bottom card (pushed down with `margin-top: auto`): background `#1f1f1f`, radius 6px,
  padding 12px, gap 8px. Title "Collectie-scan" 13px/700; body 11px `#b3b3b3`,
  `line-height: 1.5`: "Laatste scan 12 min geleden · 8.412 tracks in Rekordbox."; white pill
  button height 30px, 12px/700, "Opnieuw scannen".

**Main pane** — background `#121212`, padding `28px 32px 48px`, vertical scroll.
Content column `max-width: 1180px`, flex column, gap 24–28px.

### 1. Match-overzicht
Purpose: review how a Spotify playlist maps onto the Rekordbox collection and resolve
ambiguous matches.

- **Hero**: flex row, gap 20px, `align-items: flex-end`, wraps. 132×132 artwork block,
  radius 6px, `linear-gradient(135deg, #af2896, #509bf5)`. Text stack gap 10px:
  eyebrow "SPOTIFY PLAYLIST · MATCH-RAPPORT" 11px/700 `#b3b3b3` tracking 0.08em;
  title "Warehouse Winter 2026" 24px/700, `line-height: 1.2`;
  meta 13px `#b3b3b3`: "128 tracks · 96 in collectie · 14 twijfelgevallen · 18 ontbreken".
  Right-aligned action row (wraps, gap 8px): ghost pill "Exporteer XML"
  (height 34px, `1px solid #333333`, transparent, hover border `#ffffff`) and white pill
  "Ontbrekende naar wachtrij" (height 34px) which navigates to the buy queue.
- **Stat cards**: 4-column grid, gap 12px. Each: `#1f1f1f`, radius 6px, padding 16px,
  gap 6px — label 11px `#b3b3b3` tracking 0.04em, value 24px/700, note 11px `#73777c`.
  1) IN COLLECTIE / 96 (value in `#1ed760`) / "75% van de playlist"
  2) TWIJFEL / 14 / "remix of edit onduidelijk"
  3) ONTBREEKT / 18 / "16 te koop gevonden"
  4) GEEN ANALYSE / 7 / "BPM/key ontbreekt"
- **Filter row**: pill chips height 30px, padding `0 14px`, radius 9999px, 12px/700.
  Selected = white bg / black text ("Alles"); others `#1f1f1f` white text, hover `#292929`
  ("Ontbreekt", "Twijfel", "In collectie"). Right side: "Sorteer op zekerheid" 12px `#b3b3b3`.
- **Missing group**: heading row = 8px dot `#b85850` + "Ontbreekt in Rekordbox" 14px/700 +
  "18 tracks" 12px `#b3b3b3`. Column header and rows share
  `grid-template-columns: 32px minmax(0, 1fr) 110px 60px 52px 180px`, gap 16px.
  Header: 11px `#73777c`, tracking 0.06em, padding `0 16px 8px`,
  `border-bottom: 1px solid #1f1f1f`, labels "# / TRACK / LABEL / BPM / KEY / ACTIE".
  Rows: background `#1f1f1f`, radius 6px, padding `10px 16px`, hover `#292929`;
  index 12px `#73777c`; 40×40 cover placeholder `#292929`; title 13px/600 ellipsis;
  artist 12px `#b3b3b3`; label/BPM/key 12px `#b3b3b3`; action cell right-aligned with
  store+price 11px `#73777c` and a white pill (height 30px, 12px/700).
  Demo rows (title / artist / label / bpm / key / store / CTA):
  - 01 Hydraulic (Original Mix) / Anna Kovač / Ostgut Ton / 134 / 7A / Beatport € 1,79 / In wachtrij
  - 02 Static Bloom / Tolga Ergün / Dystopian / 132 / 11B / Bandcamp € 2,10 / In wachtrij
  - 03 Concrete Sunrise — Vertigo Edit / Marit de Vries / Kompakt / 128 / 4A / Traxsource € 2,49 / In wachtrij
  - 04 Nightbus / Ferro & Lien / Eigen release / 126 / 9B / Niet gevonden / Zoek handmatig
  - 05 Untitled B2 / Kamera / White label / 137 / 2A / Discogs € 14,00 / Bekijk
- **Uncertain group**: heading = 8px dot `#c5c5c5` + "Twijfelgevallen — jouw beslissing"
  14px/700 + "14 tracks". Each card: `#1f1f1f`, radius 6px, padding `14px 16px`, grid
  `minmax(0,1fr) 40px minmax(0,1fr) 180px`, gap 16px, items centered.
  Left = Spotify side (eyebrow "SPOTIFY" 11px `#73777c` tracking 0.06em, title 13px/600,
  "artist · duration · year" 12px `#b3b3b3`), middle = match score 13px/700 `#1ed760`,
  right = Rekordbox side (eyebrow "REKORDBOX", title, "duration · BPM · key").
  Actions right-aligned: ghost pill "Andere", white pill "Bevestig" (both height 30px).
  Demo rows: Falling Light (Extended) / Sora Watanabe / 7:12 · 2024 — 84% — Falling Light
  (Original Mix) / 6:48 · 130 BPM · 5A; Ember / Bas Hollander / 5:30 · 2025 — 71% —
  Ember (Rework) / 6:02 · 128 BPM · 8B; Ritual Machine / VETA / 6:44 · 2023 — 68% —
  Ritual Machine (VETA Live Dub) / 8:10 · 136 BPM · 1A.

### 2. Koop-wachtrij (buy queue)
Purpose: buy the missing tracks, grouped per store, and know what happens after purchase.

- Header stack gap 8px: eyebrow "KOOP-WACHTRIJ"; title "Ontbrekende tracks afrekenen"
  24px/700; body 13px `#b3b3b3`: "Per winkel gegroepeerd. Na aankoop landen bestanden in je
  watch-folder en importeert Rekordbox ze automatisch."
- Two-column shell: `grid-template-columns: minmax(0, 1fr) minmax(240px, 300px)`, gap 24px,
  `align-items: start`. Should stack below roughly 1100px.
- **Store card**: `#1f1f1f`, radius 6px, `overflow: hidden`.
  Header row padding `14px 16px`, `border-bottom: 1px solid #292929`: store name 14px/700,
  count badge (11px `#b3b3b3`, padding `3px 10px`, radius 9999px, background `#292929`,
  "<n> tracks"), spacer, total 13px/700, format 11px `#73777c`.
  Item rows: grid `22px minmax(0,1fr) 90px 70px 80px`, gap 16px, padding `10px 16px`,
  `border-bottom: 1px solid #292929`, hover `#292929`. Checkbox = 15×15,
  `border-radius: 2px`, background `#1ed760`, black ✓ 10px/700. Title 13px/600,
  artist 12px `#b3b3b3`, "bpm · key" and quality 12px `#b3b3b3`, price 13px/600 right-aligned.
  Demo stores: Beatport (9 tracks, € 15,21, WAV 24-bit), Bandcamp (5 tracks, € 9,14, FLAC),
  Traxsource (2 tracks, € 4,98, AIFF), with the item rows listed in the prototype's logic class.
- **Summary panel** (sticky, `top: 0`), `#1f1f1f`, radius 6px, padding 16px, gap 14px:
  "Overzicht" 14px/700; rows 13px `#b3b3b3` space-between — "16 tracks / € 26,84"
  (value white), "2 niet vindbaar / uitgesloten", and a total row with
  `border-top: 1px solid #333333`, padding-top 8px, 700 white "Totaal / € 26,84".
  White pill height 36px "Afrekenen per winkel"; footnote 11px `#73777c`, line-height 1.5:
  "Je wordt per winkel doorgestuurd; de wachtrij houdt bij wat al is voldaan."
- **After-purchase card**: "Na aankoop" 13px/700, three 12px `#b3b3b3` lines:
  "Bestanden naar ~/Music/Rekordbox Inbox", "Automatisch analyseren (BPM + key)",
  "Toevoegen aan playlist Warehouse Winter 2026".

### 3. Playlist builder
Purpose: shape the matched tracks into a structured set and push it back to Rekordbox.

- Header: eyebrow "PLAYLIST BUILDER"; title "Warehouse Winter 2026 — setstructuur" 24px/700;
  body "Vier fases, 2u14 speelduur, harmonisch geordend op Camelot."; right white pill
  height 34px "Naar Rekordbox sturen".
- **Energy curve card**: `#1f1f1f`, radius 6px, padding 20px, gap 14px.
  Title row: "Energiecurve" 14px/700, "122 → 138 BPM" 12px `#b3b3b3`, spacer,
  "Elke balk is één track" 11px `#73777c`.
  Bars: flex row, `align-items: flex-end`, gap 3px, container height 120px. One bar per
  track: `flex: 1`, `border-radius: 2px`, height = energy percentage, background `#535353`;
  bars inside the peak window are `#1ed760`; hover turns a bar `#1ed760`.
  Prototype curve (30 values, %): 22 26 30 34 38 42 44 48 52 56 60 64 70 74 78 82 88 92 96
  100 98 94 90 86 80 72 64 54 44 34; indices 16–21 highlighted as peak.
  Phase ruler below: grid `22% 30% 30% 18%`, gap 3px, labels 11px `#b3b3b3`
  "Warmup / Build / Peak / Outro".
- **Phase columns**: 4-column grid, gap 12px, `align-items: start`. Card `#1f1f1f`, radius 6px.
  Header padding `14px 14px 12px`, `border-bottom: 1px solid #292929`: phase name 14px/700 +
  duration 11px `#b3b3b3` on the right, then rule text 11px `#73777c`.
  Track rows: flex row, gap 10px, padding `9px 14px`, `border-bottom: 1px solid #292929`,
  `cursor: grab`, hover `#292929`. Index 11px `#535353` (14px wide), title 12px/600 ellipsis,
  artist 11px `#b3b3b3` ellipsis, right stack: BPM 11px `#ffffff`, key 10px `#1ed760`.
  Footer drop hint "+ track slepen" 11px `#73777c`, padding `10px 14px`.
  Phases: Warmup (28 min, "122–126 BPM · lage energie"), Build (41 min,
  "128–132 BPM · +1 key per stap"), Peak (46 min, "133–138 BPM · hoge energie"),
  Outro (19 min, "afbouw naar 126 BPM"); 4/4/4/3 demo tracks, numbered 1–15.
- **Checks bar**: `#1f1f1f`, radius 6px, padding 16px, flex row gap 20px:
  "Controles" 13px/700, then 12px `#b3b3b3` items "3 key-conflicten tussen Build en Peak",
  "1 track zonder cue-points", "2 tracks nog niet gekocht"; right ghost pill height 30px
  "Voorstel automatisch herordenen".

## Interactions & Behavior
Implemented in the prototype:
- Sidebar workspace items switch the main pane between the three views; the active item takes
  the `#292929` background and white text.
- "Ontbrekende naar wachtrij" in the match hero navigates to the buy queue.
- "In wachtrij" on a missing-track row increments the sidebar buy counter (starts at 16).
- Hover states: sidebar rows `#1f1f1f`, nav items and table rows `#292929`, white pills
  `#e6e6e6`, ghost pills border `#ffffff`, energy bars `#1ed760`.
- Sticky summary panel in the buy queue.

Intended but not built (implement in the app):
- Filter chips filtering the match table; "Sorteer op zekerheid" sort control.
- "Bevestig" accepting a candidate match and moving the row into the matched group;
  "Andere" opening a candidate picker with alternative Rekordbox matches.
- Drag-and-drop of tracks between phase columns, and "Voorstel automatisch herordenen"
  producing a reordered set that resolves key conflicts.
- Store checkout hand-off, purchase tracking, watch-folder import, Rekordbox XML export.
- Loading state for the collection scan and playlist match run (progress with track count),
  empty state for an unscanned playlist, and error states for API/auth failures and
  unreadable Rekordbox libraries.
- Responsive: below ~1100px the buy-queue shell should stack; below ~1280px the phase grid
  should drop to two columns.

## State Management
Prototype state: `view: "match" | "buy" | "build"` and `buy: number` (queue count).

Real implementation needs at minimum:
- Auth/session for Spotify; a connection handle for the local Rekordbox library
  (XML export or database path) with a "last scan" timestamp and track count.
- `collection`: normalized Rekordbox tracks (title, artist, mix/version, label, duration,
  BPM, key, file path, cue-point presence, analysis status).
- `playlists`: Spotify playlists with per-playlist scan status.
- `matchReport` per playlist: rows with status `matched | uncertain | missing | unanalyzed`,
  a confidence score, and candidate matches for uncertain rows.
- `buyQueue`: items grouped by store with price, format, quality, purchase state.
- `setPlan`: ordered phases, each with rules (BPM range, energy target, key stepping) and
  track ordering; derived validation results for the checks bar.
- Matching itself is server/worker work: fuzzy title+artist matching with mix/version and
  duration tolerance produces the score shown in the UI.

## Design Tokens
Source: `DESIGN.md` (Spotify-derived reference), included in this bundle.

Colours: canvas `#000000`; surfaces `#121212` (sidebar/main), `#1f1f1f` (cards/inputs),
`#292929` (hover/active); borders `#333333`, `#535353`; text `#ffffff` primary,
`#b3b3b3` secondary, `#73777c` muted, `#c5c5c5` captions, `#535353` faint;
accent `#1ed760` (green — active/positive), `#b85850` (signal red, supporting only);
promo gradient `linear-gradient(90deg, #af2896, #509bf5)` (used for the playlist artwork).

Spacing (4px base): 4, 8, 12, 16, 20, 24, 28, 32, 40, 48.

Typography: Inter (substitute for SpotifyMixUI), weights 400/600/700.
Sizes used: 10, 11, 12, 13, 14, 15, 24. Line heights 1.2 / 1.33 / 1.5.
Tracking: 0.08em on eyebrow labels, 0.06em on table headers, 0.04em on stat labels,
-0.01em on the wordmark. Never exceed 24px for headings.

Radii: 2px small (checkbox, energy bars), 6px content cards and images,
500px inputs and avatars, 9999px buttons and chips.

Elevation: none. Depth comes from surface colour steps only — no drop shadows,
no decorative card borders.

## Assets
No real assets. Album artwork, artist images and the sidebar playlist covers are placeholder
blocks (`#292929`, radius 6px) and one gradient block; the ♫, ⌕ and ✓ marks are text glyphs.
Replace covers with Spotify artwork URLs and Rekordbox artwork, and the glyphs with the
codebase's icon set (monoline, white on dark, small and functional).

## Files
- `Rekordbox Matcher.dc.html` — the full prototype (all three views, demo data, view state).
- `DESIGN.md` — the style reference the design follows (tokens, components, do's and don'ts).
- `theme.css`, `variables.css`, `tokens.json` — token files supplied with the style reference.
