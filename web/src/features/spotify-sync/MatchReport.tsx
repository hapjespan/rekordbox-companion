import { formatPosition } from "./format";
import { TRACK_STATUS_LABELS, TRACK_STATUS_ORDER } from "./types";
import type { SyncTotals, TrackStatus } from "./types";

interface MatchReportTrack {
  position: number;
  artist: string;
  title: string;
  status: TrackStatus;
}

interface MatchReportProps {
  totals: SyncTotals;
  tracks: MatchReportTrack[];
}

// The delivered design's row anatomy, shared by both tables below: a 40x40
// cover placeholder (there is no artwork URL on either side of a match yet,
// so it stays the prototype's own placeholder block), the title at 13px/600
// and the artist at 12px muted.
function TrackCell({ artist, title }: { artist: string; title: string }) {
  return (
    <div className="flex min-w-0 items-center gap-12">
      <span
        aria-hidden="true"
        className="flex h-40 w-40 flex-none items-center justify-center rounded-md bg-smoke text-body-sm text-steel"
      >
        ♫
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-body font-semibold text-pure-white">{title}</span>
        <span className="truncate text-body-sm text-mist">{artist}</span>
      </span>
    </div>
  );
}

const ROW = "bg-graphite hover:bg-smoke";
const CELL_LEADING = "py-10 pr-8 pl-16";
const CELL_MIDDLE = "px-8 py-10";
const CELL_TRAILING = "py-10 pr-16 pl-8";
const HEAD_CELL = "text-caption tracking-table pb-8 text-left font-bold text-mist";

interface MissingTracksProps {
  tracks: MatchReportTrack[];
  // The design's per-row action leads to the buy queue ("In wachtrij").
  onGoToBuyQueue: () => void;
}

// The design's Missing group (HANDOFF.md: "Missing group"), minus three of its
// six columns.
//
// LABEL, BPM and KEY are deliberately absent: for a track that is NOT in the
// Rekordbox collection none of those three values exists anywhere in this
// system. There is no local file to have been analysed, Spotify's
// audio-features endpoint answers 403 for this application (verified), and the
// iTunes/Apple Music store lookup that fills the buy queue returns a link, a
// preview and a price -- never a BPM, a key or a label. Rendering the columns
// with an em dash in every cell would be three columns of nothing, so the grid
// is 32px / 1fr / 180px instead of the design's
// 32px / 1fr / 110px / 60px / 52px / 180px.
//
// The ACTIE cell also drops the design's store name and price: those live on
// the Missing Track row that GET /api/missing serves (FR-041), and that payload
// carries no `sync_track_id`, so there is no reliable key to join a store link
// onto a row of this table. The Koop-wachtrij view shows them per store.
export function MissingTracks({ tracks, onGoToBuyQueue }: MissingTracksProps) {
  if (tracks.length === 0) {
    return <p className="text-body text-mist">Geen ontbrekende nummers in deze synchronisatie.</p>;
  }

  return (
    <table className="w-full table-fixed border-separate border-spacing-y-8">
      <caption className="sr-only">Nummers die ontbreken in de Rekordbox-collectie</caption>
      <thead>
        <tr>
          <th scope="col" className={`${HEAD_CELL} w-[var(--spacing-32)] pr-8 pl-16`}>
            #
          </th>
          <th scope="col" className={`${HEAD_CELL} px-8`}>
            TRACK
          </th>
          <th scope="col" className={`${HEAD_CELL} w-[var(--spacing-180)] pr-16 pl-8 text-right`}>
            ACTIE
          </th>
        </tr>
      </thead>
      <tbody>
        {tracks.map((track) => (
          <tr key={track.position} className={ROW}>
            <td className={`${CELL_LEADING} rounded-l-md align-middle text-body-sm text-mist`}>
              {formatPosition(track.position)}
            </td>
            <td className={`${CELL_MIDDLE} align-middle`}>
              <TrackCell artist={track.artist} title={track.title} />
            </td>
            <td className={`${CELL_TRAILING} rounded-r-md align-middle`}>
              <div className="flex flex-col items-end gap-4">
                {/* Where the design shows the store and the price. Those are
                    per-Missing-Track data (FR-041) this table cannot key onto,
                    so the cell says where they live instead of guessing. */}
                <span className="text-caption text-mist">Koop via de wachtrij</span>
                <button
                  type="button"
                  onClick={onGoToBuyQueue}
                  className="inline-flex h-30 min-w-24 items-center justify-center rounded-full-2 bg-pure-white px-14 text-body-sm font-bold whitespace-nowrap text-void-black hover:bg-chalk focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
                >
                  Naar wachtrij
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// T032: per-track status and totals, keyboard-operable (a plain table is
// natively keyboard-navigable, no custom widgets needed), focus always
// visible, AA contrast, 24x24 targets. Status is conveyed as Dutch text,
// never colour alone (WCAG; web/tests/features/spotify-sync/
// MatchReport.test.tsx, T023, pins these exact labels and the
// "label: count" totals format).
//
// This is the design's collection group: the tracks that are not missing and
// no longer under review. `rejected` and `unmatchable` ride along here rather
// than in an invented fourth group, which is why the status column stays --
// it is the only thing that distinguishes those rows from a real match.
export function MatchReport({ totals, tracks }: MatchReportProps) {
  return (
    <div className="flex flex-col gap-16">
      <ul className="flex flex-wrap gap-16 text-body text-pure-white" aria-label="Totalen">
        {TRACK_STATUS_ORDER.map((status) => (
          <li key={status}>
            {TRACK_STATUS_LABELS[status]}: {totals[status]}
          </li>
        ))}
      </ul>
      <table className="w-full table-fixed border-separate border-spacing-y-8">
        <caption className="sr-only">Matchresultaten per nummer</caption>
        <thead>
          <tr>
            <th scope="col" className={`${HEAD_CELL} w-[var(--spacing-32)] pr-8 pl-16`}>
              #
            </th>
            <th scope="col" className={`${HEAD_CELL} px-8`}>
              TRACK
            </th>
            <th scope="col" className={`${HEAD_CELL} w-[var(--spacing-180)] pr-16 pl-8`}>
              STATUS
            </th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((track) => (
            <tr key={track.position} className={ROW}>
              <td className={`${CELL_LEADING} rounded-l-md align-middle text-body-sm text-mist`}>
                {formatPosition(track.position)}
              </td>
              <td className={`${CELL_MIDDLE} align-middle`}>
                <TrackCell artist={track.artist} title={track.title} />
              </td>
              <td className={`${CELL_TRAILING} rounded-r-md align-middle text-body-sm text-mist`}>
                {TRACK_STATUS_LABELS[track.status]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
