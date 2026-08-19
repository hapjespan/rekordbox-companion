import { useState } from "react";

import { PlayerBar, type PlayerBarTrack } from "../components/PlayerBar";
import type { SelectedRekordboxPlaylist } from "../components/RekordboxLibrary";
import { TrackTable } from "../components/TrackTable";

interface CollectionViewProps {
  // Seeded by the top bar's search field; the token makes a repeated search
  // for the same term re-seed the table.
  seedQuery: string;
  seedToken: number;
  // Bumped when the sidebar's Collectie-scan card finishes a rebuild.
  reloadToken: number;
  // Set when the DJ picked a playlist in the sidebar's Rekordbox tree: the
  // same table, over that playlist's tracks only.
  playlist: SelectedRekordboxPlaylist | null;
  onShowWholeCollection: () => void;
}

const GHOST_PILL =
  "inline-flex h-30 w-fit items-center justify-center rounded-full-2 border border-iron bg-transparent px-16 text-body-sm font-bold whitespace-nowrap text-pure-white hover:border-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

// US5 (browse and play the Collection). The prototype has no view for it --
// its three views cover the Spotify side only -- so this view follows the
// same shell conventions (eyebrow-less header, then the panel) rather than a
// delivered design of its own.
//
// The player sits inside this view: it is the collection browser's own
// transport (FR-025), and leaving the view stops playback, which is the
// honest behaviour for a preview player.
export function CollectionView({
  seedQuery,
  seedToken,
  reloadToken,
  playlist,
  onShowWholeCollection,
}: CollectionViewProps) {
  const [playingTrack, setPlayingTrack] = useState<PlayerBarTrack | null>(null);

  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        {/* Which set of tracks is on screen is said in words, never implied by
            a filtered table alone. */}
        {playlist && (
          <p className="text-caption font-bold tracking-eyebrow text-mist">REKORDBOX-PLAYLIST</p>
        )}
        <h1 className="text-heading leading-heading font-bold text-pure-white">
          {playlist ? playlist.name : "Collectie"}
        </h1>
        <p className="text-body text-mist">
          {playlist
            ? "Alleen de nummers uit deze Rekordbox-playlist, in de volgorde die je in Rekordbox hebt gemaakt."
            : "Zoek, sorteer en beluister de nummers die Rekordbox in je collectie heeft."}
        </p>
        {playlist && (
          <button type="button" onClick={onShowWholeCollection} className={GHOST_PILL}>
            Hele collectie tonen
          </button>
        )}
      </div>

      <TrackTable
        onPlay={setPlayingTrack}
        seedQuery={seedQuery}
        seedToken={seedToken}
        reloadToken={reloadToken}
        playlistId={playlist?.id ?? null}
      />
      <PlayerBar track={playingTrack} />
    </div>
  );
}
