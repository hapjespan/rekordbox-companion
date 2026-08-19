import { useEffect, useRef, useState } from "react";

import { apiClient } from "./api/client";
import type { SelectedRekordboxPlaylist } from "./components/RekordboxLibrary";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { asApiResponse } from "./features/spotify-sync/types";
import type {
  SpotifyConnectionStatus,
  SyncSession,
  SyncSessionDetail,
} from "./features/spotify-sync/types";
import type { NavCounter, ViewId } from "./navigation";
import { BuyQueueView } from "./views/BuyQueueView";
import { CollectionView } from "./views/CollectionView";
import { EnrichmentView } from "./views/EnrichmentView";
import { MatchOverviewView } from "./views/MatchOverviewView";
import { PlaylistBuilderView } from "./views/PlaylistBuilderView";

// The application shell from the delivered design (web/design-input/
// HANDOFF.md, "Shell"): a 300px sidebar beside a scrolling main pane, under a
// full-width 64px top bar, on the black canvas.
//
// It wraps the seven user stories that already exist; the five WORKSPACE
// views (navigation.ts) are the only way to reach them, which is the
// guarantee tests/App.test.tsx exists to keep: US2 and US5 both once shipped
// as fully tested components that nothing mounted, so neither story existed
// for the DJ. A view that no nav item reaches is the same bug.
export function App() {
  const [view, setView] = useState<ViewId>("match");
  const [session, setSession] = useState<SyncSessionDetail | null>(null);
  const [spotifyStatus, setSpotifyStatus] = useState<SpotifyConnectionStatus | null>(null);
  const [openMissingCount, setOpenMissingCount] = useState<number | null>(null);
  const [collectionSeed, setCollectionSeed] = useState({ query: "", token: 0 });
  // The Rekordbox playlist the Collection view is filtered to, or null for the
  // whole collection.
  const [rekordboxPlaylist, setRekordboxPlaylist] = useState<SelectedRekordboxPlaylist | null>(
    null,
  );
  const [collectionReloadToken, setCollectionReloadToken] = useState(0);
  const [focusUrlToken, setFocusUrlToken] = useState(0);
  const mainRef = useRef<HTMLElement>(null);

  // The sidebar's buy-queue counter. Re-read on every view switch: the
  // number changes whenever the DJ resolves a row in the Koop-wachtrij view,
  // and this is the one place that knows a view switch happened.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data, error } = await apiClient.GET("/api/missing", {
          params: { query: { status: "open" } },
        });
        if (cancelled) return;
        const items = error ? undefined : asApiResponse<unknown[] | undefined>(data);
        setOpenMissingCount(Array.isArray(items) ? items.length : null);
      } catch {
        if (!cancelled) setOpenMissingCount(null);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [view]);

  // A switched view starts at the top of its own pane, not halfway down the
  // previous one's scroll position.
  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [view]);

  async function refreshSession(sessionId: number) {
    const { data } = await apiClient.GET("/api/sync/sessions/{session_id}", {
      params: { path: { session_id: sessionId } },
    });
    setSession(asApiResponse<SyncSessionDetail>(data));
  }

  async function handleSessionCreated(created: SyncSession) {
    await refreshSession(created.id);
  }

  // Started from the sidebar's Spotify list: the report is what the DJ asked
  // for, so the view switches to it rather than leaving the result off screen.
  function handleSidebarSessionCreated(created: SyncSession) {
    setView("match");
    void handleSessionCreated(created);
  }

  function handleSearch(query: string) {
    setView("collection");
    // A search is a search of the whole collection: leaving a playlist filter
    // silently in place would make the result set a lie.
    setRekordboxPlaylist(null);
    setCollectionSeed((current) => ({ query, token: current.token + 1 }));
  }

  function handleRekordboxPlaylistSelected(playlist: SelectedRekordboxPlaylist) {
    setView("collection");
    setRekordboxPlaylist(playlist);
    // A new playlist starts unfiltered: the previous playlist's search term
    // has no meaning in this one.
    setCollectionSeed((current) => ({ query: "", token: current.token + 1 }));
  }

  function handleShowWholeCollection() {
    setRekordboxPlaylist(null);
    setCollectionSeed((current) => ({ query: "", token: current.token + 1 }));
  }

  function handleSyncRequested() {
    setView("match");
    setFocusUrlToken((token) => token + 1);
  }

  // Counters only where a real number exists (navigation.ts): the match count
  // comes from the loaded session, the buy count from GET /api/missing. The
  // prototype's "4 fases" on the builder is demo data -- a structure's phase
  // count only exists once one is generated -- so that item carries none.
  const counters: Partial<Record<ViewId, NavCounter>> = {};
  if (session) counters.match = { value: String(session.tracks.length) };
  if (openMissingCount !== null) counters.buy = { value: String(openMissingCount), accent: true };

  return (
    <div className="grid h-screen grid-cols-[var(--spacing-300)_minmax(0,1fr)] grid-rows-[var(--spacing-64)_minmax(0,1fr)] overflow-hidden bg-void-black font-spotifymixui text-pure-white">
      <TopBar
        spotifyStatus={spotifyStatus}
        onSearch={handleSearch}
        onSyncRequested={handleSyncRequested}
      />

      <Sidebar
        activeView={view}
        onNavigate={setView}
        counters={counters}
        onCollectionScanned={() => setCollectionReloadToken((token) => token + 1)}
        onSessionCreated={handleSidebarSessionCreated}
        onRekordboxPlaylistSelected={handleRekordboxPlaylistSelected}
        rekordboxPlaylistId={rekordboxPlaylist?.id ?? null}
      />

      <main ref={mainRef} className="overflow-y-auto bg-carbon px-32 pt-28 pb-48">
        <div className="flex max-w-[var(--spacing-1180)] flex-col">
          {view === "match" && (
            <MatchOverviewView
              session={session}
              onSessionCreated={(created) => void handleSessionCreated(created)}
              onSessionChanged={() => {
                if (session) void refreshSession(session.id);
              }}
              onSpotifyStatus={setSpotifyStatus}
              onGoToBuyQueue={() => setView("buy")}
              focusUrlToken={focusUrlToken}
            />
          )}
          {view === "buy" && <BuyQueueView />}
          {view === "build" && <PlaylistBuilderView />}
          {view === "collection" && (
            <CollectionView
              seedQuery={collectionSeed.query}
              seedToken={collectionSeed.token}
              reloadToken={collectionReloadToken}
              playlist={rekordboxPlaylist}
              onShowWholeCollection={handleShowWholeCollection}
            />
          )}
          {view === "enrichment" && <EnrichmentView />}
        </div>
      </main>
    </div>
  );
}
