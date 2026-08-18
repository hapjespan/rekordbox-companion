import { MissingQueue } from "../features/missing/MissingQueue";

// The prototype's Koop-wachtrij view (HANDOFF.md, "2. Koop-wachtrij"),
// carrying US4 (link the missing tracks to the Apple Music / iTunes Store).
//
// Deliberately not built, because the data and the scope do not exist:
// - the per-store cards, the store totals, the price, format and quality
//   columns and the row checkboxes -- a Missing Track carries an Apple Music
//   / iTunes link and a status, nothing else (FR-020..FR-022, ADR 0006);
// - the "Overzicht" summary panel with its running total and the "Afrekenen
//   per winkel" checkout -- the app never handles money or a cart (FR-023);
// - the "Na aankoop" watch-folder card -- there is no watch-folder import,
//   and writing to Rekordbox happens only through the guarded writer
//   (ADR 0008).
export function BuyQueueView() {
  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <p className="text-caption font-bold tracking-eyebrow text-mist">KOOP-WACHTRIJ</p>
        <h1 className="text-heading leading-heading font-bold text-pure-white">
          Ontbrekende nummers
        </h1>
        <p className="text-body text-mist">
          Elk ontbrekend nummer krijgt een Apple Music / iTunes-link. Jij houdt per nummer bij of
          het is aangeschaft of genegeerd.
        </p>
      </div>

      <MissingQueue />
    </div>
  );
}
