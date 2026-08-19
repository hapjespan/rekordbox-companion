import type { ChecksResult } from "./phaseModel";

// The design's "Controles" bar, with the checks that are actually computable
// instead of the design's illustrative ones (no cue-point data is read from
// Rekordbox, and no energy value exists):
//
// - musical-key conflicts on the seam between two adjacent phases, from the
//   verbatim Rekordbox Camelot notation;
// - tracks missing a BPM or a key, which in this collection is the normal case
//   and therefore worth counting rather than hiding;
// - tracks that still sit in the buy queue as an open item.
//
// Every item states its count in words, so nothing here is conveyed by colour.
// "Voorstel automatisch herordenen" is deliberately absent: the owner chose
// the option without a reordering algorithm.

export interface ChecksBarProps {
  checks: ChecksResult;
}

function keyConflictText(checks: ChecksResult): string {
  if (checks.key_conflicts.length === 0) return "Geen toonaard-conflicten op de fase-overgangen";
  const detail = checks.key_conflicts
    .map(
      (conflict) =>
        `${conflict.from_phase} → ${conflict.to_phase} (${conflict.from_key} → ${conflict.to_key})`,
    )
    .join(", ");
  return `${checks.key_conflicts.length} toonaard-conflict(en) op de fase-overgangen: ${detail}`;
}

export function ChecksBar({ checks }: ChecksBarProps) {
  const items = [
    keyConflictText(checks),
    checks.uncomparable_seams > 0
      ? `${checks.uncomparable_seams} fase-overgang(en) niet te vergelijken: geen Camelot-toonaard`
      : null,
    `${checks.without_bpm} nummer(s) zonder BPM in Rekordbox`,
    `${checks.without_key} nummer(s) zonder toonaard in Rekordbox`,
    checks.unresolved > 0
      ? `${checks.unresolved} nummer(s) waarvan BPM en toonaard niet opgehaald konden worden`
      : null,
    checks.in_buy_queue.length === 0
      ? "Geen nummers meer in de koop-wachtrij"
      : `${checks.in_buy_queue.length} nummer(s) staan nog in de koop-wachtrij: ${checks.in_buy_queue
          .map((track) => `${track.artist} – ${track.title}`)
          .join(", ")}`,
  ].filter((item): item is string => item !== null);

  return (
    <section aria-labelledby="checks-title" className="rounded-md bg-graphite p-16">
      <div className="flex flex-wrap items-baseline gap-20">
        <h2 id="checks-title" className="text-body font-bold text-pure-white">
          Controles
        </h2>
        <ul className="flex flex-wrap gap-20">
          {items.map((item) => (
            <li key={item} className="text-body-sm text-mist">
              {item}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
