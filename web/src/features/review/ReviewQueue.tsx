import { useEffect, useRef, useState } from "react";

interface ReviewCandidate {
  rb_content_id: string;
  score: number;
  artist: string;
  title: string;
}

interface ReviewItem {
  sync_track_id: number;
  spotify_artist: string;
  spotify_title: string;
  candidates: ReviewCandidate[];
}

type PreviewTarget =
  { kind: "candidate"; rbContentId: string } | { kind: "spotify"; syncTrackId: number };

interface ReviewQueueProps {
  items: ReviewItem[];
  onAccept: (syncTrackId: number, rbContentId: string) => void;
  onReject: (syncTrackId: number) => void;
  onPreview: (target: PreviewTarget) => void;
}

function candidateDomId(item: ReviewItem, candidate: ReviewCandidate): string {
  return `review-candidate-${item.sync_track_id}-${candidate.rb_content_id}`;
}

// T039: keyboard wiring for FR-011 (arrows navigate, A accepts, R rejects,
// space previews). The container holds real DOM focus for the whole
// session -- it is never re-mounted or blurred when items resolve and drop
// out of the list, which is what "focus never lost" (spec.md US2) means in
// practice; aria-activedescendant names the active candidate for assistive
// tech (WAI-ARIA APG listbox pattern, ReviewQueue.test.tsx/T035 finding).
export function ReviewQueue({ items, onAccept, onReject, onPreview }: ReviewQueueProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [activeCandidateIndex, setActiveCandidateIndex] = useState(0);

  const clampedItemIndex = items.length === 0 ? 0 : Math.min(activeItemIndex, items.length - 1);
  const activeItem = items[clampedItemIndex] as ReviewItem | undefined;
  const clampedCandidateIndex = activeItem
    ? Math.min(activeCandidateIndex, activeItem.candidates.length - 1)
    : 0;
  const activeCandidate = activeItem?.candidates[clampedCandidateIndex];

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
      case "ArrowDown":
        event.preventDefault();
        setActiveItemIndex((i) => Math.min(i + 1, items.length - 1));
        setActiveCandidateIndex(0);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveItemIndex((i) => Math.max(i - 1, 0));
        setActiveCandidateIndex(0);
        break;
      case "ArrowRight":
        event.preventDefault();
        setActiveCandidateIndex((i) => Math.min(i + 1, activeItem.candidates.length - 1));
        break;
      case "ArrowLeft":
        event.preventDefault();
        setActiveCandidateIndex((i) => Math.max(i - 1, 0));
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
        event.preventDefault();
        if (activeCandidate)
          onPreview({ kind: "candidate", rbContentId: activeCandidate.rb_content_id });
        break;
      default:
        break;
    }
  }

  return (
    <div
      ref={containerRef}
      data-testid="review-queue"
      role="listbox"
      aria-label="Review wachtrij"
      tabIndex={0}
      aria-activedescendant={
        activeItem && activeCandidate ? candidateDomId(activeItem, activeCandidate) : undefined
      }
      onKeyDown={handleKeyDown}
      className="flex flex-col gap-16 text-body-lg text-pure-white outline-none"
    >
      {items.map((item, itemIndex) => {
        const isActiveItem = itemIndex === clampedItemIndex;
        return (
          <div
            key={item.sync_track_id}
            data-testid="review-queue-item"
            // WAI-ARIA 1.2 lists `group` as a required-owned-element of
            // `listbox`, specifically for grouping `option`s (the listbox
            // analogue of a native <optgroup>) -- not a departure from the
            // pattern.
            role="group"
            aria-label={`${item.spotify_artist} - ${item.spotify_title}`}
            aria-current={isActiveItem ? "true" : undefined}
            className={`flex flex-col gap-8 rounded-md p-16 ${
              isActiveItem ? "bg-graphite" : "bg-smoke"
            }`}
          >
            <p className="text-mist">
              Origineel: {item.spotify_artist} – {item.spotify_title}
            </p>
            <ul className="flex flex-col gap-4">
              {item.candidates.map((candidate, candidateIndex) => {
                const isActiveCandidate = isActiveItem && candidateIndex === clampedCandidateIndex;
                return (
                  <li
                    key={candidate.rb_content_id}
                    id={candidateDomId(item, candidate)}
                    data-testid="review-queue-candidate"
                    role="option"
                    aria-selected={isActiveCandidate}
                    className={isActiveCandidate ? "text-spotify-green" : undefined}
                  >
                    {candidate.artist} – {candidate.title} · score {candidate.score}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
