import { useEffect, useId, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";
import type { MissingTrackDto, MissingTrackStatus } from "./types";

const STATUS_LABELS: Record<MissingTrackStatus, string> = {
  open: "Open",
  acquired: "Aangeschaft",
  ignored: "Genegeerd",
};

const STATUS_ORDER: MissingTrackStatus[] = ["open", "acquired", "ignored"];

// Same code-keyed-switch convention as PlaylistUrlForm.tsx's
// errorMessageFor: Dutch text for known codes, the raw (English) backend
// message only as a last resort (review finding: this previously always
// fell back to raw backend text).
function overrideErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "missing_field":
      return "Vul een Apple Music / iTunes-link in.";
    case "missing_track_not_found":
      return "Dit ontbrekende nummer bestaat niet meer.";
    default:
      return error.message || "Kon de link niet opslaan. Probeer het opnieuw.";
  }
}

interface MissingTrackRowProps {
  track: MissingTrackDto;
  onStatusChange: (id: number, status: MissingTrackStatus) => void;
  onLinkOverride: (id: number, url: string) => Promise<ApiError | null>;
}

// T059 (FR-020..FR-022, WCAG): status conveyed in text (STATUS_LABELS),
// never colour alone; the manual override input reports errors by naming
// the field and the fix (spec.md's naming-input criterion, same pattern as
// PlaylistUrlForm/T031).
function MissingTrackRow({ track, onStatusChange, onLinkOverride }: MissingTrackRowProps) {
  const [draftUrl, setDraftUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const inputId = useId();
  const errorId = useId();

  async function handleOverrideSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const url = draftUrl.trim();
    if (!url) {
      setError("Vul een Apple Music / iTunes-link in.");
      return;
    }
    const apiError = await onLinkOverride(track.id, url);
    if (apiError) {
      setError(overrideErrorMessageFor(apiError));
      return;
    }
    setError(null);
    setDraftUrl("");
  }

  async function handleCopy() {
    if (!track.effective_url) return;
    await navigator.clipboard.writeText(track.effective_url);
    setCopied(true);
  }

  return (
    <li
      data-testid="missing-track-row"
      className="flex flex-col gap-8 rounded-md bg-graphite p-16 text-pure-white"
    >
      <p className="text-body-lg font-semibold">
        {track.artist} – {track.title}
      </p>
      <p className="text-body-lg text-mist">Status: {STATUS_LABELS[track.status]}</p>

      <div className="flex flex-wrap gap-8" role="group" aria-label="Status wijzigen">
        {STATUS_ORDER.map((status) => (
          <button
            key={status}
            type="button"
            aria-pressed={track.status === status}
            onClick={() => onStatusChange(track.id, status)}
            className={`min-h-24 rounded-full-2 border border-iron px-12 py-8 text-body-lg font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green ${
              track.status === status
                ? "bg-pure-white text-void-black"
                : "bg-transparent text-pure-white"
            }`}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
      </div>

      {track.effective_url ? (
        <div className="flex flex-wrap items-center gap-8">
          <a
            href={track.effective_url}
            target="_blank"
            rel="noreferrer"
            className="text-body-lg text-spotify-green underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            Open in Apple Music
          </a>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            {copied ? "Gekopieerd" : "Kopieer link"}
          </button>
        </div>
      ) : (
        <p className="text-body-lg text-mist">Geen link gevonden.</p>
      )}

      <form onSubmit={(event) => void handleOverrideSubmit(event)} className="flex flex-col gap-8">
        <label htmlFor={inputId} className="text-body-lg font-semibold">
          Handmatige link
        </label>
        <div className="flex flex-wrap gap-8">
          <input
            id={inputId}
            type="text"
            value={draftUrl}
            onChange={(event) => setDraftUrl(event.target.value)}
            placeholder="https://music.apple.com/nl/album/..."
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

export function MissingQueue() {
  const [tracks, setTracks] = useState<MissingTrackDto[] | null>(null);

  async function refresh() {
    // A network-level failure (not an HTTP error response, which
    // openapi-fetch already surfaces as `data: undefined, error: {...}`)
    // rejects the fetch call itself; since this queue is mounted
    // unconditionally on every page (T107 finding), it must degrade to
    // "show nothing yet" rather than crash the rest of the page. The `?? []`
    // on the success branch covers the HTTP-error case the same way
    // (`data` is `undefined` there too) -- both failure shapes end up as an
    // empty queue rather than a render crash on `tracks.length`.
    try {
      const { data } = await apiClient.GET("/api/missing", {
        params: { query: { status: "open" } },
      });
      setTracks(asApiResponse<MissingTrackDto[]>(data) ?? []);
    } catch {
      setTracks((current) => current ?? []);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleStatusChange(id: number, status: MissingTrackStatus) {
    await apiClient.POST("/api/missing/{missing_id}/status", {
      params: { path: { missing_id: id } },
      body: { status },
    });
    await refresh();
  }

  async function handleLinkOverride(id: number, url: string): Promise<ApiError | null> {
    const { error } = await apiClient.POST("/api/missing/{missing_id}/link", {
      params: { path: { missing_id: id } },
      body: { itunes_url: url },
    });
    if (error) return asApiResponse<ApiError>(error);
    await refresh();
    return null;
  }

  async function handleRefreshLinks() {
    await apiClient.POST("/api/missing/refresh-links");
    await refresh();
  }

  if (tracks === null) {
    return (
      <p role="status" className="text-body-lg text-mist">
        Ontbrekende nummers laden…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-16">
      <div className="flex items-center justify-between gap-16">
        <p className="text-heading font-bold">Ontbrekende nummers</p>
        <button
          type="button"
          onClick={() => void handleRefreshLinks()}
          className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          Links vernieuwen
        </button>
      </div>

      {tracks.length === 0 ? (
        <p className="text-body-lg text-mist">Geen openstaande ontbrekende nummers.</p>
      ) : (
        <ul className="flex flex-col gap-16">
          {tracks.map((track) => (
            <MissingTrackRow
              key={track.id}
              track={track}
              onStatusChange={(id, status) => void handleStatusChange(id, status)}
              onLinkOverride={handleLinkOverride}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
