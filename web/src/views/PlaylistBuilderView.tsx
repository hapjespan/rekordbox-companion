import { BookingWorkspace } from "../features/bookings/BookingWorkspace";

// The prototype's Playlist builder view (HANDOFF.md, "3. Playlist builder"),
// carrying US7 (generate booking-type playlist structures): the header stack,
// then BookingWorkspace's BPM-verloop card, phase columns and checks bar.
//
// Two things the design shows are deliberately not here:
// - the "Energiecurve" name and an energy value per track: Spotify's
//   audio-features endpoint answers 403 for this application, so no energy
//   value exists anywhere and the card plots BPM under its own name instead;
// - "Voorstel automatisch herordenen": the owner chose the option without a
//   reordering algorithm.
//
// The design's right-hand "Naar Rekordbox sturen" pill is BookingWorkspace's
// existing "Toepassen" action, which goes through the guarded write path; it is
// not duplicated here.
export function PlaylistBuilderView() {
  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <p className="text-caption font-bold tracking-eyebrow text-mist">PLAYLIST BUILDER</p>
        <h1 className="text-heading leading-heading font-bold text-pure-white">
          Boekingstructuren
        </h1>
        <p className="text-body text-mist">
          Stel een setstructuur samen per boekingstype: geef je playlists een setfase, verdeel de
          nummers over de fases en schrijf de structuur naar Rekordbox.
        </p>
      </div>

      <BookingWorkspace />
    </div>
  );
}
