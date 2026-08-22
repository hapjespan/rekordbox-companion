import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../api/client";
import { asApiResponse } from "../features/spotify-sync/types";

interface CollectionScanCardProps {
  // The Collection view's table reloads once a rebuild lands.
  onScanned: () => void;
}

function errorMessageFor(apiError: unknown): string {
  const code = (apiError as { code?: string } | undefined)?.code;
  if (code === "rekordbox_not_found") {
    return "Rekordbox is niet gevonden. Start Rekordbox en probeer het opnieuw.";
  }
  return "Opnieuw scannen is mislukt. Probeer het opnieuw.";
}

// The sidebar's "Collectie-scan" card (HANDOFF.md, "Sidebar" bottom card),
// pushed to the bottom with margin-top: auto.
//
// This is the app's ONE collection-rebuild control. TrackTable used to carry
// a "Collectie verversen" button of its own (added in the phase 7 review,
// because the index is an on-demand in-memory cache -- ADR 0012 -- and
// nothing ever demanded it); the delivered design puts that control here, so
// the button moved and the table now points at this card instead.
//
// The track count is the collection's real total (GET /api/collection returns
// it alongside the page), not the prototype's demo "8.412". The last-scan
// time is recorded here when a rebuild completes; the backend keeps no
// scanned-at timestamp, so before the first scan of a session there is
// nothing to report rather than a made-up "12 min geleden".
export function CollectionScanCard({ onScanned }: CollectionScanCardProps) {
  const [total, setTotal] = useState<number | null>(null);
  const [lastScan, setLastScan] = useState<Date | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTotal = useCallback(async () => {
    try {
      // limit=1 keeps this a count query: only `total` is read.
      const { data, error: apiError } = await apiClient.GET("/api/collection", {
        params: { query: { limit: 1 } },
      });
      if (apiError) {
        setTotal(null);
        return;
      }
      const body = asApiResponse<{ total: number } | undefined>(data);
      setTotal(body?.total ?? null);
    } catch {
      setTotal(null);
    }
  }, []);

  useEffect(() => {
    // Fetching on mount, not deriving a value from render: react-hooks 7
    // flags the setState inside `loadTotal`, but there is nothing to compute
    // during render here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadTotal();
  }, [loadTotal]);

  async function handleScan() {
    setScanning(true);
    try {
      const { error: apiError } = await apiClient.POST("/api/collection/reindex", {});
      if (apiError) {
        setError(errorMessageFor(apiError));
        return;
      }
      setError(null);
      setLastScan(new Date());
      await loadTotal();
      onScanned();
    } catch {
      setError(errorMessageFor(undefined));
    } finally {
      setScanning(false);
    }
  }

  const trackCount =
    total === null ? "aantal onbekend" : `${total.toLocaleString("nl-NL")} tracks in Rekordbox`;
  // Three states, not two: the index survives this page, so it can already hold
  // tracks that were indexed before this tab existed. Saying "nog niet gescand"
  // next to a real track count contradicts itself, and the moment genuinely is
  // unknown -- the app records it here, not in the backend.
  const scanMoment =
    lastScan !== null
      ? `Laatste scan ${lastScan.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}`
      : total !== null && total > 0
        ? "Scanmoment onbekend"
        : "Nog niet gescand";

  return (
    <div className="mt-auto flex flex-col gap-8 rounded-md bg-graphite p-12">
      <h2 className="text-body font-bold text-pure-white">Collectie-scan</h2>
      <p className="text-caption leading-body text-mist">
        {scanMoment} · {trackCount}.
      </p>
      <button
        type="button"
        onClick={() => void handleScan()}
        disabled={scanning}
        className="inline-flex h-30 items-center justify-center rounded-full-2 bg-pure-white px-12 text-body-sm font-bold whitespace-nowrap text-void-black hover:bg-chalk focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:bg-iron disabled:text-mist"
      >
        {scanning ? "Scannen…" : "Opnieuw scannen"}
      </button>
      {error && (
        <p role="alert" className="text-caption leading-body text-pure-white">
          {error}
        </p>
      )}
    </div>
  );
}
