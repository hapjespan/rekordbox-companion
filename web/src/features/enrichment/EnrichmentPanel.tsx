import { useEffect, useId, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";
import type { EnrichmentStatusDto, UnenrichedTrackDto } from "./types";

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

function startErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "enrichment_already_running":
      return "Er loopt al een verrijking.";
    default:
      return error.message || "Kon de verrijking niet starten. Probeer het opnieuw.";
  }
}

// While a run is in progress, poll GET /status as a safety net alongside
// SSE (review finding): run_until_drained can end via
// MAX_CONSECUTIVE_FAILED_BATCHES with tracks still remaining, and the one
// terminal SSE event that does fire for that last chunk can race the
// background task's own flag-clear on the server. Either way, this poll
// converges on the real "running" state within one interval even with no
// (or a stale) SSE signal.
const STATUS_POLL_INTERVAL_MS = 3000;

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
  const [startError, setStartError] = useState<string | null>(null);

  // Derived from the server's own `running` flag (review finding), never
  // from a plain local `useState`: a reload mid-run, a second tab, or a run
  // started before this page loaded all report their real state as soon as
  // `status` loads, instead of showing an enabled button with a run already
  // going on behind it.
  const isRunning = status?.running ?? false;

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
    // Fetching on mount; nothing here is derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshStatus();
    void refreshUnenriched();
  }, []);

  // R4: enrichment runs for hours, so progress streams over the existing
  // SSE channel rather than polling. Every chunk's event now refetches
  // status/the work list -- not only the last one -- so the status line and
  // coverage number move live during a multi-hour run instead of staying
  // frozen until a completion probe fires (review finding).
  useEffect(() => {
    const source = new EventSource("/api/events");
    function handleProgress() {
      void refreshStatus();
      void refreshUnenriched();
    }
    source.addEventListener("enrichment_progress", handleProgress);
    return () => source.close();
  }, []);

  // Safety net alongside SSE (review finding): run_until_drained can end
  // via MAX_CONSECUTIVE_FAILED_BATCHES with tracks still remaining, and the
  // one terminal SSE event that does fire can race the server clearing its
  // own "running" flag. Polling while a run is in progress guarantees the
  // button re-enables within one interval regardless of what SSE did or
  // didn't deliver.
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => void refreshStatus(), STATUS_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isRunning]);

  async function handleStart() {
    setStartError(null);
    // Optimistic: disable the button the instant the user clicks, before
    // the POST round-trip even resolves, so a fast double-click can't fire
    // twice. Reverted below if the server refuses the run.
    setStatus((current) => (current ? { ...current, running: true } : current));
    const { error } = await apiClient.POST("/api/enrichment/run");
    if (error) {
      setStatus((current) => (current ? { ...current, running: false } : current));
      setStartError(startErrorMessageFor(asApiResponse<ApiError>(error)));
    }
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
        {/* The panel title is the Genre-verrijking view's own <h1> now. */}
        <div>
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

      {startError && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          {startError}
        </p>
      )}

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
