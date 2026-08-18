import { useId } from "react";

import { NAV_ITEMS } from "../navigation";
import type { NavCounter, ViewId } from "../navigation";
import { CollectionScanCard } from "./CollectionScanCard";

interface SidebarProps {
  activeView: ViewId;
  onNavigate: (view: ViewId) => void;
  counters: Partial<Record<ViewId, NavCounter>>;
  onCollectionScanned: () => void;
}

// The shell's sidebar (HANDOFF.md, "Sidebar"): the WORKSPACE view switcher
// and the collection-scan card at the bottom.
//
// The prototype's second block, "SPOTIFY PLAYLISTS", is deliberately absent:
// no endpoint lists the operator's Spotify playlists (contracts/api.md -- the
// app takes a pasted playlist URL, FR-002), so every row of it would be
// invented. The Rekordbox playlist tree GET /api/playlists returns is a
// different thing and is not a substitute.
export function Sidebar({ activeView, onNavigate, counters, onCollectionScanned }: SidebarProps) {
  const workspaceLabelId = useId();

  return (
    <aside className="flex flex-col gap-24 overflow-y-auto bg-carbon px-12 py-20">
      <nav aria-labelledby={workspaceLabelId} className="flex flex-col gap-2">
        {/* Kept in the design's own wording, as delivered. */}
        <h2
          id={workspaceLabelId}
          className="px-12 pb-8 text-caption font-bold tracking-eyebrow text-mist"
        >
          WORKSPACE
        </h2>
        <ul className="flex flex-col gap-2">
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
      </nav>

      <CollectionScanCard onScanned={onCollectionScanned} />
    </aside>
  );
}
