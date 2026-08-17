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

// T032: per-track status and totals, keyboard-operable (a plain table is
// natively keyboard-navigable, no custom widgets needed), focus always
// visible, AA contrast, 24x24 targets (no interactive targets in a
// read-only report, so nothing to size here). Status is conveyed as Dutch
// text, never colour alone (WCAG; web/tests/features/spotify-sync/
// MatchReport.test.tsx, T023, pins these exact labels and the
// "label: count" totals format).
const STATUS_LABELS: Record<TrackStatus, string> = {
  matched: "Gematcht",
  review: "Controleren",
  missing: "Ontbreekt",
  rejected: "Afgewezen",
  unmatchable: "Niet matchbaar",
};

const TOTALS_ORDER: TrackStatus[] = ["matched", "review", "missing", "rejected", "unmatchable"];

export function MatchReport({ totals, tracks }: MatchReportProps) {
  return (
    <div className="flex flex-col gap-16">
      <ul className="flex flex-wrap gap-16 text-body-lg text-pure-white" aria-label="Totalen">
        {TOTALS_ORDER.map((status) => (
          <li key={status}>
            {STATUS_LABELS[status]}: {totals[status]}
          </li>
        ))}
      </ul>
      <table className="w-full border-collapse text-body-lg text-pure-white">
        <caption className="sr-only">Matchresultaten per nummer</caption>
        <thead>
          <tr>
            <th scope="col" className="px-8 py-8 text-left text-mist">
              Artiest
            </th>
            <th scope="col" className="px-8 py-8 text-left text-mist">
              Titel
            </th>
            <th scope="col" className="px-8 py-8 text-left text-mist">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((track) => (
            <tr key={track.position} className="border-t border-iron">
              <td className="px-8 py-8">{track.artist}</td>
              <td className="px-8 py-8">{track.title}</td>
              <td className="px-8 py-8">{STATUS_LABELS[track.status]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
