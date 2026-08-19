import { useId, useState } from "react";

import { NAV_ITEMS } from "../navigation";
import type { NavCounter, ViewId } from "../navigation";
import { CollectionScanCard } from "./CollectionScanCard";
import { RekordboxLibrary } from "./RekordboxLibrary";
import type { SelectedRekordboxPlaylist } from "./RekordboxLibrary";
import { SpotifyPlaylistList } from "./SpotifyPlaylistList";
import type { SyncSession } from "../features/spotify-sync/types";

interface SidebarProps {
  activeView: ViewId;
  onNavigate: (view: ViewId) => void;
  counters: Partial<Record<ViewId, NavCounter>>;
  onCollectionScanned: () => void;
  // A Spotify row starts a sync; the shell loads the report and switches view.
  onSessionCreated: (session: SyncSession) => void;
  // A Rekordbox row filters the Collection view to that playlist.
  onRekordboxPlaylistSelected: (playlist: SelectedRekordboxPlaylist) => void;
  rekordboxPlaylistId: string | null;
}

interface SidebarSectionProps {
  label: string;
  children: React.ReactNode;
}

// One sidebar section: the design's 11px/700 tracking label, then a box that
// scrolls on its own.
//
// Bounded scrolling per section is what keeps this sidebar usable with 101
// Spotify playlists and a deep Rekordbox tree: the two lists share the space
// left between the WORKSPACE nav and the Collectie-scan card and each scrolls
// inside it, so neither list can push the other -- or the nav, or the card --
// out of reach. The <aside> itself never scrolls.
//
// The label folds its section away as well, which is how one source gets the
// whole middle when the DJ is working out of it. Folded, not unmounted: the
// list keeps what it fetched, so folding costs no request.
function SidebarSection({ label, children }: SidebarSectionProps) {
  const labelId = useId();
  const [open, setOpen] = useState(true);

  return (
    <div className={`flex flex-col gap-8 ${open ? "min-h-0 flex-1" : "flex-none"}`}>
      <h2 className="px-12">
        <button
          type="button"
          id={labelId}
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          className="flex min-h-24 w-full items-center gap-8 text-caption font-bold tracking-eyebrow text-mist hover:text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          {/* The fold state is a shape and an aria-expanded, never a colour. */}
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          <span>{label}</span>
        </button>
      </h2>
      <div
        role="group"
        aria-labelledby={labelId}
        hidden={!open}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {children}
      </div>
    </div>
  );
}

// The shell's sidebar (HANDOFF.md, "Sidebar"): the WORKSPACE view switcher,
// both playlist sources below it, and the collection-scan card at the bottom.
//
// The two sources are deliberately separate blocks, not one merged list: a
// Spotify playlist is something to match against the collection, a Rekordbox
// playlist is a slice of the collection itself, and the actions differ.
//
// Landmark structure: one navigation landmark for the whole column, with the
// three sections marked by their headings and labelled groups. Three nested
// navs would leave the page with no single "the nav" to reach the workspace
// from, which is the guarantee tests/App.test.tsx exists to keep.
export function Sidebar({
  activeView,
  onNavigate,
  counters,
  onCollectionScanned,
  onSessionCreated,
  onRekordboxPlaylistSelected,
  rekordboxPlaylistId,
}: SidebarProps) {
  const workspaceLabelId = useId();

  return (
    <aside className="flex min-h-0 flex-col gap-24 overflow-hidden bg-carbon px-12 py-20">
      <nav aria-label="Zijbalk" className="flex min-h-0 flex-1 flex-col gap-24">
        <div className="flex flex-none flex-col gap-2">
          {/* Kept in the design's own wording, as delivered. */}
          <h2
            id={workspaceLabelId}
            className="px-12 pb-8 text-caption font-bold tracking-eyebrow text-mist"
          >
            WORKSPACE
          </h2>
          <ul aria-labelledby={workspaceLabelId} className="flex flex-col gap-2">
            {NAV_ITEMS.map((item) => {
              const isActive = item.id === activeView;
              const counter = counters[item.id];
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    // The current view is announced, not merely coloured
                    // (WCAG 1.4.1 / 4.1.2).
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => onNavigate(item.id)}
                    className={`flex w-full items-center justify-between gap-8 rounded-md px-12 py-9 text-left text-body font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green ${
                      isActive
                        ? "bg-smoke text-pure-white"
                        : "bg-transparent text-mist hover:bg-smoke hover:text-pure-white"
                    }`}
                  >
                    <span>{item.label}</span>
                    {counter && (
                      <span
                        className={`text-caption ${
                          counter.accent ? "font-bold text-spotify-green" : "text-mist"
                        }`}
                      >
                        {counter.value}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <SidebarSection label="SPOTIFY PLAYLISTS">
          <SpotifyPlaylistList onSessionCreated={onSessionCreated} />
        </SidebarSection>

        <SidebarSection label="REKORDBOX-BIBLIOTHEEK">
          <RekordboxLibrary
            onSelect={onRekordboxPlaylistSelected}
            selectedId={rekordboxPlaylistId}
          />
        </SidebarSection>
      </nav>

      <CollectionScanCard onScanned={onCollectionScanned} />
    </aside>
  );
}
