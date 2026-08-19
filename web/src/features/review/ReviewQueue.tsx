import { useEffect, useRef, useState } from "react";

import { formatDuration } from "../spotify-sync/format";

interface ReviewCandidate {
  rb_content_id: string;
  score: number;
  // Optional on purpose: the backend's `SyncTrack.candidates` rows carry
  // `{rb_content_id, score, reason}` only (contracts/api.md, engine
  // matching/engine.py). The Rekordbox side of the delivered design needs the
  // track itself, so ReviewView resolves these fields through
  // GET /api/collection (useCandidateDetails.ts) and passes them down here.
  // Whatever it could not resolve stays undefined, and the card then names
  // the candidate by the Rekordbox id the DJ can look up -- never a guess.
  artist?: string;
  title?: string;
  duration_ms?: number | null;
  bpm?: number | null;
  musical_key?: string | null;
}

interface ReviewItem {
  sync_track_id: number;
  spotify_artist: string;
  spotify_title: string;
  spotify_duration_ms?: number | null;
  candidates: ReviewCandidate[];
}

type PreviewTarget =
  { kind: "candidate"; rbContentId: string } | { kind: "spotify"; syncTrackId: number };

interface ReviewQueueProps {
  items: ReviewItem[];
  onAccept: (syncTrackId: number, rbContentId: string) => void;
  onReject: (syncTrackId: number) => void;
  onPreview: (target: PreviewTarget) => void;
  // Lets a parent mirror the keyboard selection (ReviewView feeds it to
  // DualPlayback) without taking ownership of it: the queue holds the
  // focus and the selection, the parent only observes. Must be a stable
  // callback (useCallback) -- it is an effect dependency here.
  onActiveChange?: (syncTrackId: number | null, rbContentId: string | null) => void;
}

function candidateDomId(item: ReviewItem, candidate: ReviewCandidate): string {
  return `review-candidate-${item.sync_track_id}-${candidate.rb_content_id}`;
}

// Falls back to the Rekordbox id when the candidate carries no artist/title
// (see ReviewCandidate): identifying a candidate by the id the DJ can look
// up in Rekordbox beats rendering an empty dash.
function candidateLabel(candidate: ReviewCandidate): string {
  if (candidate.artist && candidate.title) return `${candidate.artist} – ${candidate.title}`;
  return `Rekordbox-id ${candidate.rb_content_id}`;
}

// The Rekordbox side of the card titles the candidate the way the design
// does: the Rekordbox track title alone (the artist is on the Spotify side of
// the same row), or the id when the lookup could not resolve it.
function candidateTitle(candidate: ReviewCandidate): string {
  return candidate.title ?? `Rekordbox-id ${candidate.rb_content_id}`;
}

// The design's Rekordbox meta line: "duration · BPM · key", with only the
// parts that exist. An unresolved candidate says so instead of showing three
// em dashes that read like missing analysis data.
function candidateMeta(candidate: ReviewCandidate | undefined): string {
  if (!candidate) return "Geen kandidaat";
  const parts: string[] = [];
  const duration = formatDuration(candidate.duration_ms);
  if (duration) parts.push(duration);
  if (candidate.bpm !== null && candidate.bpm !== undefined) parts.push(`${candidate.bpm} BPM`);
  if (candidate.musical_key) parts.push(candidate.musical_key);
  if (parts.length === 0) return "Niet gevonden in de collectie";
  return parts.join(" · ");
}

function spotifyMeta(item: ReviewItem): string {
  const duration = formatDuration(item.spotify_duration_ms);
  return duration ? `${item.spotify_artist} · ${duration}` : item.spotify_artist;
}

const EYEBROW = "text-caption tracking-table font-bold text-mist";
const SIDE_TITLE = "truncate text-body font-semibold text-pure-white";
const SIDE_META = "truncate text-body-sm text-mist";
const GHOST_PILL =
  "inline-flex h-30 min-w-24 items-center justify-center rounded-full-2 border border-iron bg-transparent px-14 text-body-sm font-bold whitespace-nowrap text-pure-white hover:border-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50";
const WHITE_PILL =
  "inline-flex h-30 min-w-24 items-center justify-center rounded-full-2 bg-pure-white px-14 text-body-sm font-bold whitespace-nowrap text-void-black hover:bg-chalk focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50";

// T039: keyboard wiring for FR-011 (arrows navigate, A accepts, R rejects,
// space previews). The container holds real DOM focus for the whole
// session -- it is never re-mounted or blurred when items resolve and drop
// out of the list, which is what "focus never lost" (spec.md US2) means in
// practice; aria-activedescendant names the active candidate for assistive
// tech (ReviewQueue.test.tsx/T035 finding).
//
// Each item is the delivered design's side-by-side card (HANDOFF.md,
// "Uncertain group"): the Spotify original left, the match score in the
// middle, the Rekordbox candidate right, the two actions ("Andere",
// "Bevestig") right-aligned. Below them sits the candidate picker the design
// notes as intended-but-not-built: every candidate the backend returned, as a
// row of its own, which is also what keeps the whole candidate list -- not
// just the selected one -- available to assistive tech and to the mouse.
//
// The container is a `group` rather than a `listbox`: the cards hold real
// buttons, and a listbox may only own options and groups, so the option
// semantics live on the candidate picker inside each card (a labelled
// listbox per card) and `aria-activedescendant` on the container points at
// the one active option.
export function ReviewQueue({
  items,
  onAccept,
  onReject,
  onPreview,
  onActiveChange,
}: ReviewQueueProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  // The candidate selection is stored together with the item it belongs to
  // and only read back while that same item still occupies the active
  // position. That resets the selection to the first candidate in the very
  // same render in which a DIFFERENT item takes over the position -- which
  // is what happens when the parent removes the item A/R just resolved.
  // Doing it in render rather than in an effect leaves no interim render in
  // which a rapid follow-up A would accept a non-first candidate of the
  // next item (review finding).
  const [candidateSelection, setCandidateSelection] = useState<{
    itemId: number | null;
    index: number;
  }>({ itemId: null, index: 0 });

  const clampedItemIndex = items.length === 0 ? 0 : Math.min(activeItemIndex, items.length - 1);
  const activeItem = items[clampedItemIndex] as ReviewItem | undefined;
  const activeItemId = activeItem?.sync_track_id ?? null;
  const selectedCandidateIndex =
    candidateSelection.itemId === activeItemId ? candidateSelection.index : 0;
  const clampedCandidateIndex = activeItem
    ? Math.min(selectedCandidateIndex, activeItem.candidates.length - 1)
    : 0;
  const activeCandidate = activeItem?.candidates[clampedCandidateIndex];
  const activeRbContentId = activeCandidate?.rb_content_id ?? null;

  useEffect(() => {
    onActiveChange?.(activeItemId, activeRbContentId);
  }, [activeItemId, activeRbContentId, onActiveChange]);

  // React's `autoFocus` prop relies on the browser's native autofocus
  // behaviour, which only fires for nodes present at initial page parse --
  // not for nodes React inserts into an already-mounted document (jsdom
  // included). Focusing explicitly on mount is what actually holds real
  // DOM focus on the container from the start (spec.md US2, T035 finding).
  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  // `activeItemIndex` is a plain position, not a stable id -- correct only
  // because the parent may ever remove the ACTIVE item (the one A/R just
  // resolved), never an arbitrary other one: onAccept/onReject always
  // target `activeItem.sync_track_id`, so there's no path by which a
  // non-active item disappears out from under this index.
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!activeItem) return;

    switch (event.key) {
      // ArrowUp/ArrowDown need no explicit candidate reset: landing on
      // another item already yields candidate 0, because the stored
      // selection belongs to the item it was made on.
      case "ArrowDown":
        event.preventDefault();
        setActiveItemIndex((i) => Math.min(i + 1, items.length - 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveItemIndex((i) => Math.max(i - 1, 0));
        break;
      case "ArrowRight":
        event.preventDefault();
        setCandidateSelection({
          itemId: activeItem.sync_track_id,
          index: Math.min(clampedCandidateIndex + 1, activeItem.candidates.length - 1),
        });
        break;
      case "ArrowLeft":
        event.preventDefault();
        setCandidateSelection({
          itemId: activeItem.sync_track_id,
          index: Math.max(clampedCandidateIndex - 1, 0),
        });
        break;
      case "a":
      case "A":
        if (activeCandidate) onAccept(activeItem.sync_track_id, activeCandidate.rb_content_id);
        break;
      case "r":
      case "R":
        onReject(activeItem.sync_track_id);
        break;
      case " ":
        // A focused card button owns space itself (that is how a button is
        // activated); previewing on the same press would fire two actions from
        // one key. Every other key is unambiguous and keeps working wherever
        // the focus sits inside the queue.
        if ((event.target as HTMLElement).closest("button") !== null) break;
        event.preventDefault();
        if (activeCandidate)
          onPreview({ kind: "candidate", rbContentId: activeCandidate.rb_content_id });
        break;
      default:
        break;
    }
  }

  // Every pointer interaction hands focus straight back to the container.
  // Without that, a click would leave DOM focus on a button that the very
  // next render unmounts (the resolved card disappears), which is exactly
  // the "focus is never lost" guarantee this queue is built around.
  function select(itemIndex: number, candidateIndex: number) {
    setActiveItemIndex(itemIndex);
    const item = items[itemIndex];
    if (item) setCandidateSelection({ itemId: item.sync_track_id, index: candidateIndex });
    containerRef.current?.focus();
  }

  return (
    <div
      ref={containerRef}
      data-testid="review-queue"
      role="group"
      aria-label="Review wachtrij"
      tabIndex={0}
      aria-activedescendant={
        activeItem && activeCandidate ? candidateDomId(activeItem, activeCandidate) : undefined
      }
      onKeyDown={handleKeyDown}
      className="flex flex-col gap-12 outline-none"
    >
      {items.map((item, itemIndex) => {
        const isActiveItem = itemIndex === clampedItemIndex;
        const selectedIndex = isActiveItem ? clampedCandidateIndex : 0;
        const selectedCandidate = item.candidates[selectedIndex] as ReviewCandidate | undefined;
        return (
          <div
            key={item.sync_track_id}
            data-testid="review-queue-item"
            aria-current={isActiveItem ? "true" : undefined}
            // The active card is marked by an outline (a shape, present in
            // high-contrast and colour-blind viewing alike) on top of the
            // colour, and its selected candidate row below is bold and
            // underlined -- never colour alone (US2's WCAG criteria).
            className={`flex flex-col gap-12 rounded-md bg-graphite px-16 py-14 md:grid md:grid-cols-[minmax(0,1fr)_var(--spacing-40)_minmax(0,1fr)_var(--spacing-180)] md:items-center md:gap-16 ${
              isActiveItem ? "outline outline-2 outline-offset-2 outline-spotify-green" : ""
            }`}
          >
            <div className="flex min-w-0 flex-col gap-4">
              <p className={EYEBROW}>SPOTIFY</p>
              <p className={SIDE_TITLE}>{item.spotify_title}</p>
              <p className={SIDE_META}>{spotifyMeta(item)}</p>
            </div>

            {/* The design's bare percentage in the middle column. The label is
                visually hidden rather than absent: read on its own, out of the
                two-column layout, "84%" says nothing about what it measures. */}
            <div className="text-body font-bold text-spotify-green">
              <span className="sr-only">Matchscore </span>
              {selectedCandidate ? `${selectedCandidate.score}%` : "–"}
            </div>

            <div className="flex min-w-0 flex-col gap-4">
              <p className={EYEBROW}>REKORDBOX</p>
              <p className={SIDE_TITLE}>
                {selectedCandidate ? candidateTitle(selectedCandidate) : "Geen kandidaat"}
              </p>
              <p className={SIDE_META}>{candidateMeta(selectedCandidate)}</p>
            </div>

            <div className="flex flex-wrap justify-end gap-8">
              {/* A roving tab order: only the active card's two actions are
                  tab stops, so reaching a card deep in a long queue stays one
                  Tab away instead of two per card above it (the same technique
                  components/TrackTable.tsx uses for its row actions). The
                  arrows move which card that is. */}
              <button
                type="button"
                tabIndex={isActiveItem ? 0 : -1}
                disabled={item.candidates.length < 2}
                onClick={() => select(itemIndex, (selectedIndex + 1) % item.candidates.length)}
                className={GHOST_PILL}
              >
                Andere
              </button>
              <button
                type="button"
                tabIndex={isActiveItem ? 0 : -1}
                disabled={!selectedCandidate}
                onClick={() => {
                  if (!selectedCandidate) return;
                  select(itemIndex, selectedIndex);
                  onAccept(item.sync_track_id, selectedCandidate.rb_content_id);
                }}
                className={WHITE_PILL}
              >
                Bevestig
              </button>
            </div>

            {/* Rendered only when there is something to own: a listbox with
                no options is an ARIA violation, not an empty list. */}
            {item.candidates.length > 0 && (
              <ul
                role="listbox"
                aria-label={`Kandidaten voor ${item.spotify_artist} – ${item.spotify_title}`}
                className="flex flex-col gap-4 md:col-span-full"
              >
                {item.candidates.map((candidate, candidateIndex) => {
                  const isActiveCandidate =
                    isActiveItem && candidateIndex === clampedCandidateIndex;
                  return (
                    <li
                      key={candidate.rb_content_id}
                      id={candidateDomId(item, candidate)}
                      data-testid="review-queue-candidate"
                      role="option"
                      aria-selected={isActiveCandidate}
                      onClick={() => select(itemIndex, candidateIndex)}
                      className={`text-body-sm ${
                        isActiveCandidate
                          ? "font-bold text-spotify-green underline"
                          : "text-mist hover:text-pure-white"
                      }`}
                    >
                      {candidateLabel(candidate)} · score {candidate.score}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
