import { useState } from "react";

import { PlayerBar, type PlayerBarTrack } from "../components/PlayerBar";
import { TrackTable } from "../components/TrackTable";

interface CollectionViewProps {
  // Seeded by the top bar's search field; the token makes a repeated search
  // for the same term re-seed the table.
  seedQuery: string;
  seedToken: number;
  // Bumped when the sidebar's Collectie-scan card finishes a rebuild.
  reloadToken: number;
}

// US5 (browse and play the Collection). The prototype has no view for it --
// its three views cover the Spotify side only -- so this view follows the
// same shell conventions (eyebrow-less header, then the panel) rather than a
// delivered design of its own.
//
// The player sits inside this view: it is the collection browser's own
// transport (FR-025), and leaving the view stops playback, which is the
// honest behaviour for a preview player.
export function CollectionView({ seedQuery, seedToken, reloadToken }: CollectionViewProps) {
  const [playingTrack, setPlayingTrack] = useState<PlayerBarTrack | null>(null);

  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <h1 className="text-heading leading-heading font-bold text-pure-white">Collectie</h1>
        <p className="text-body text-mist">
          Zoek, sorteer en beluister de nummers die Rekordbox in je collectie heeft.
        </p>
      </div>

      <TrackTable
        onPlay={setPlayingTrack}
        seedQuery={seedQuery}
        seedToken={seedToken}
        reloadToken={reloadToken}
      />
      <PlayerBar track={playingTrack} />
    </div>
  );
}
