import { TRACK_STATUS_LABELS, TRACK_STATUS_ORDER } from "../spotify-sync/types";
import type { SyncTotals } from "../spotify-sync/types";

interface QueueCompleteProps {
  totals: SyncTotals;
}

// T041 (spec.md US2 acceptance scenario 6): once the last unresolved item
// is resolved, the DJ sees a completion state with the session's updated
// totals -- not just an empty queue. `role="status"` announces the moment
// itself to assistive tech; the totals list reuses MatchReport's labels/
// order so the same numbers read identically wherever they appear.
export function QueueComplete({ totals }: QueueCompleteProps) {
  return (
    <div role="status" className="flex flex-col gap-16 text-body-lg text-pure-white">
      <p className="text-heading font-bold">Review afgerond</p>
      <p className="text-mist">Alle Matches in deze Sync Session zijn beoordeeld.</p>
      <ul className="flex flex-wrap gap-16" aria-label="Eindtotalen">
        {TRACK_STATUS_ORDER.map((status) => (
          <li key={status}>
            {TRACK_STATUS_LABELS[status]}: {totals[status]}
          </li>
        ))}
      </ul>
    </div>
  );
}
