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

// Dutch copy for the empty state per filter view (review finding: only the
// "open" default had reachable UI at all -- "Genegeerd"/"Aangeschaft" were
// row status choices with no way back to see what landed there).
const EMPTY_STATE_LABELS: Record<MissingTrackStatus, string> = {
  open: "Geen openstaande ontbrekende nummers.",
  acquired: "Geen aangeschafte nummers.",
  ignored: "Geen genegeerde nummers.",
};

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

// Review finding: handleStatusChange/handleRefreshLinks never inspected
// their response's error, so a failed status change or refresh left the UI
// silently unchanged (unlike the link-override path, which already named
// the field and the fix). Both now surface a Dutch message the same way.
function statusChangeErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "invalid_status":
      return "Ongeldige status.";
    case "missing_track_not_found":
      return "Dit ontbrekende nummer bestaat niet meer.";
    default:
      return error.message || "Kon de status niet wijzigen. Probeer het opnieuw.";
  }
}

function refreshLinksErrorMessageFor(error: ApiError): string {
  return error.message || "Vernieuwen van links is mislukt. Probeer het opnieuw.";
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
  // Review finding: "open" was the only reachable view -- an accidental tap
  // on "Genegeerd"/"Aangeschaft" in the per-row status control removed a
  // row from this (only) list with no way back short of the API. Default
  // stays "open" (spec-sanctioned default view); the filter group below
  // makes the other two statuses reachable.
  const [statusFilter, setStatusFilter] = useState<MissingTrackStatus>("open");
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh(status: MissingTrackStatus) {
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
        params: { query: { status } },
      });
      setTracks(asApiResponse<MissingTrackDto[]>(data) ?? []);
    } catch {
      setTracks((current) => current ?? []);
    }
  }

  useEffect(() => {
    void refresh(statusFilter);
  }, [statusFilter]);

  async function handleStatusChange(id: number, status: MissingTrackStatus) {
    const { error } = await apiClient.POST("/api/missing/{missing_id}/status", {
      params: { path: { missing_id: id } },
      body: { status },
    });
    if (error) {
      // Review finding: this used to ignore the response entirely, leaving
      // the UI silently unchanged on failure.
      setActionError(statusChangeErrorMessageFor(asApiResponse<ApiError>(error)));
      return;
    }
    setActionError(null);
    await refresh(statusFilter);
  }

  async function handleLinkOverride(id: number, url: string): Promise<ApiError | null> {
    const { error } = await apiClient.POST("/api/missing/{missing_id}/link", {
      params: { path: { missing_id: id } },
      body: { itunes_url: url },
    });
    if (error) return asApiResponse<ApiError>(error);
    await refresh(statusFilter);
    return null;
  }

  async function handleRefreshLinks() {
    const { error } = await apiClient.POST("/api/missing/refresh-links");
    if (error) {
      // Review finding: this used to ignore the response entirely -- a 500
      // (or any other failure) left the UI silently unchanged.
      setActionError(refreshLinksErrorMessageFor(asApiResponse<ApiError>(error)));
      return;
    }
    setActionError(null);
    await refresh(statusFilter);
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

      <div className="flex flex-wrap gap-8" role="group" aria-label="Filter op status">
        {STATUS_ORDER.map((status) => (
          <button
            key={status}
            type="button"
            aria-pressed={statusFilter === status}
            onClick={() => setStatusFilter(status)}
            className={`min-h-24 rounded-full-2 border border-iron px-12 py-8 text-body-lg font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green ${
              statusFilter === status
                ? "bg-pure-white text-void-black"
                : "bg-transparent text-pure-white"
            }`}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
      </div>

      {actionError && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          {actionError}
        </p>
      )}

      {tracks.length === 0 ? (
        <p className="text-body-lg text-mist">{EMPTY_STATE_LABELS[statusFilter]}</p>
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
