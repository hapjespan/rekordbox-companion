import { useEffect, useId, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";
import type { EnrichmentProgressEvent, EnrichmentStatusDto, UnenrichedTrackDto } from "./types";

// Same code-keyed-switch convention as PlaylistUrlForm.tsx/MissingQueue.tsx's
// error mappers: Dutch text for known codes, the raw backend message only
// as a last resort.
function genreErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "track_not_found":
      return "Dit nummer bestaat niet meer in de collectie.";
    default:
      return error.message || "Kon de genres niet opslaan. Probeer het opnieuw.";
  }
}

interface UnenrichedRowProps {
  track: UnenrichedTrackDto;
  onSave: (rbContentId: string, genres: string[]) => Promise<ApiError | null>;
}

// T077 (FR-028/FR-029, WCAG): the manual genre editor names the field and
// the fix on error (same pattern as MissingQueue's link override), and
// conveys manual origin as visible text -- "(handmatig)" -- never colour
// alone, since every genre this editor ever sets is manual by definition.
function UnenrichedRow({ track, onSave }: UnenrichedRowProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedGenres, setSavedGenres] = useState<string[] | null>(null);
  const inputId = useId();
  const errorId = useId();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const genres = draft
      .split(",")
      .map((genre) => genre.trim())
      .filter((genre) => genre.length > 0);
    if (genres.length === 0) {
      setError("Vul minstens één genre in.");
      return;
    }
    const apiError = await onSave(track.rb_content_id, genres);
    if (apiError) {
      setError(genreErrorMessageFor(apiError));
      return;
    }
    setError(null);
    setSavedGenres(genres);
  }

  return (
    <li className="flex flex-col gap-8 rounded-md bg-graphite p-16 text-pure-white">
      <p className="text-body-lg font-semibold">
        {track.artist} – {track.title}
      </p>

      {savedGenres && (
        <p className="text-body-lg text-mist">
          {savedGenres.map((genre) => `${genre} (handmatig)`).join(", ")}
        </p>
      )}

      <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-8">
        <label htmlFor={inputId} className="text-body-lg font-semibold">
          Genres (komma-gescheiden)
        </label>
        <div className="flex flex-wrap gap-8">
          <input
            id={inputId}
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="deep house, techno"
            aria-invalid={error !== null}
            aria-describedby={error ? errorId : undefined}
            className="min-h-24 flex-1 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white placeholder-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          />
          <button
            type="submit"
            className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            Opslaan
          </button>
        </div>
        {error && (
          <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
            {error}
          </p>
        )}
      </form>
    </li>
  );
}

export function EnrichmentPanel() {
  const [status, setStatus] = useState<EnrichmentStatusDto | null>(null);
  const [unenriched, setUnenriched] = useState<UnenrichedTrackDto[] | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  async function refreshStatus() {
    try {
      const { data } = await apiClient.GET("/api/enrichment/status");
      setStatus(asApiResponse<EnrichmentStatusDto>(data));
    } catch {
      // Degrades to "no status yet" rather than crashing the page (same
      // network-failure handling as MissingQueue.refresh).
    }
  }

  async function refreshUnenriched() {
    try {
      const { data } = await apiClient.GET("/api/enrichment/unenriched");
      const body = asApiResponse<{ items: UnenrichedTrackDto[] } | undefined>(data);
      setUnenriched(body?.items ?? []);
    } catch {
      setUnenriched((current) => current ?? []);
    }
  }

  useEffect(() => {
    void refreshStatus();
    void refreshUnenriched();
  }, []);

  // R4: enrichment runs for hours, so progress streams over the existing
  // SSE channel rather than polling (research.md R4's own rejection of
  // polling for exactly this reason). `remaining === 0` is this run's
  // completion signal -- there is no separate "run finished" event type.
  useEffect(() => {
    const source = new EventSource("/api/events");
    function handleProgress(event: MessageEvent) {
      const progress = JSON.parse(event.data as string) as EnrichmentProgressEvent;
      if (progress.remaining === 0) {
        setIsRunning(false);
        void refreshStatus();
        void refreshUnenriched();
      }
    }
    source.addEventListener("enrichment_progress", handleProgress);
    return () => source.close();
  }, []);

  async function handleStart() {
    setIsRunning(true);
    await apiClient.POST("/api/enrichment/run");
  }

  async function handleSaveGenres(rbContentId: string, genres: string[]): Promise<ApiError | null> {
    const { error } = await apiClient.PUT("/api/collection/{rb_content_id}/genres", {
      params: { path: { rb_content_id: rbContentId } },
      body: { genres },
    });
    if (error) return asApiResponse<ApiError>(error);
    // A resolved track stops feeding the manual work list (FR-029); refetch
    // so it (and the coverage numbers) reflect that immediately, rather than
    // waiting for the next SSE-driven refresh or a page reload.
    await refreshUnenriched();
    await refreshStatus();
    return null;
  }

  if (status === null || unenriched === null) {
    return (
      <p role="status" className="text-body-lg text-mist">
        Verrijkingsstatus laden…
      </p>
    );
  }

  const statusParts = [
    `${status.done} verrijkt`,
    `${status.pending} wachten`,
    `${status.none_found} niet gevonden`,
  ];
  if (status.failed > 0) statusParts.push(`${status.failed} mislukt`);

  return (
    <div className="flex flex-col gap-16">
      <div className="flex items-center justify-between gap-16">
        <div>
          <p className="text-heading font-bold">Genre-verrijking</p>
          <p className="text-body-lg text-mist">{statusParts.join(", ")}</p>
        </div>
        <div className="flex items-center gap-16">
          <p className="text-heading font-bold">{status.coverage_pct}%</p>
          <button
            type="button"
            onClick={() => void handleStart()}
            disabled={isRunning}
            className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
          >
            Verrijking starten
          </button>
        </div>
      </div>

      {unenriched.length === 0 ? (
        <p className="text-body-lg text-mist">Geen nummers zonder genre.</p>
      ) : (
        <ul className="flex flex-col gap-16">
          {unenriched.map((track) => (
            <UnenrichedRow key={track.rb_content_id} track={track} onSave={handleSaveGenres} />
          ))}
        </ul>
      )}
    </div>
  );
}
