// T100 (gate-review finding, spec.md US2 accessibility criteria): "the
// documented key map (arrows, A, R, space) is discoverable from the
// screen" -- an on-screen key map, not only something described in
// external documentation. Always visible (not a hidden/toggle-only panel):
// a screen-only key map that itself needs a keypress to reveal would fail
// the same "discoverable from the screen" criterion it exists to satisfy.
const KEYS: Array<{ keys: string; action: string }> = [
  { keys: "↑ / ↓", action: "Wissel van nummer" },
  { keys: "← / →", action: "Wissel van kandidaat" },
  { keys: "A", action: "Accepteer kandidaat" },
  { keys: "R", action: "Wijs af" },
  { keys: "Spatie", action: "Beluister" },
];

export function KeymapOverlay() {
  return (
    <div
      role="note"
      aria-label="Toetsenbordbediening"
      className="flex flex-wrap gap-16 rounded-md bg-graphite p-16 text-body-lg text-pure-white"
    >
      {KEYS.map(({ keys, action }) => (
        <p key={keys} className="flex items-center gap-8">
          <kbd className="rounded-sm border border-iron bg-smoke px-8 py-4 font-bold">{keys}</kbd>
          <span className="text-mist">{action}</span>
        </p>
      ))}
    </div>
  );
}
