import { BookingWorkspace } from "../features/bookings/BookingWorkspace";

// The prototype's Playlist builder view (HANDOFF.md, "3. Playlist builder"),
// carrying US7 (generate booking-type playlist structures).
//
// Deliberately not built, because the data and the scope do not exist:
// - the "Energiecurve" card -- no energy value exists per track, and a curve
//   drawn from anything else would be invented;
// - the per-phase BPM/key columns and the green Camelot key -- the collection
//   model carries BPM but no musical key (components/TrackTable.tsx's
//   CollectionTrackDto);
// - drag-and-drop between the phase columns and "Voorstel automatisch
//   herordenen" -- HANDOFF.md lists both as "intended but not built", and
//   both would be new features rather than this re-layout;
// - the "Controles" bar's key-conflict and cue-point checks -- neither key nor
//   cue-point presence is read from Rekordbox.
export function PlaylistBuilderView() {
  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <p className="text-caption font-bold tracking-eyebrow text-mist">PLAYLIST BUILDER</p>
        <h1 className="text-heading leading-heading font-bold text-pure-white">
          Boekingstructuren
        </h1>
        <p className="text-body text-mist">
          Stel een setstructuur samen per boekingstype en schrijf die als playlist naar Rekordbox.
        </p>
      </div>

      <BookingWorkspace />
    </div>
  );
}
