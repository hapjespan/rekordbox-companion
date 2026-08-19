import { useCallback, useEffect, useId, useRef, useState } from "react";

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

// FR-041: the price is stored as an amount plus its ISO code, never as a
// pre-formatted string, so it is formatted for the Dutch UI here. A row
// without a price simply gets none (null), never a placeholder: a track can
// be streaming-only or album-only, and inventing "0,00" would be a lie
// about what the DJ would pay.
function priceLabelFor(track: MissingTrackDto): string | null {
  if (track.itunes_price === null) return null;
  if (track.itunes_currency === null) return track.itunes_price.toFixed(2);
  try {
    return new Intl.NumberFormat("nl-NL", {
      style: "currency",
      currency: track.itunes_currency,
    }).format(track.itunes_price);
  } catch {
    // An unknown currency code makes Intl throw rather than degrade; the
    // amount plus the raw code still tells the DJ what the track costs.
    return `${track.itunes_price.toFixed(2)} ${track.itunes_currency}`;
  }
}

interface MissingTrackRowProps {
  track: MissingTrackDto;
  onStatusChange: (id: number, status: MissingTrackStatus) => void;
  onLinkOverride: (id: number, url: string) => Promise<ApiError | null>;
  // Playback state is owned by the queue, not the row (FR-041: one preview
  // at a time), so a row only reports what the DJ asked for and renders
  // whether it is the row currently sounding.
  isPreviewPlaying: boolean;
  onPreviewChange: (id: number, playing: boolean) => void;
}

// T059 (FR-020..FR-022, WCAG): status conveyed in text (STATUS_LABELS),
// never colour alone; the manual override input reports errors by naming
// the field and the fix (spec.md's naming-input criterion, same pattern as
// PlaylistUrlForm/T031).
function MissingTrackRow({
  track,
  onStatusChange,
  onLinkOverride,
  isPreviewPlaying,
  onPreviewChange,
}: MissingTrackRowProps) {
  const [draftUrl, setDraftUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const inputId = useId();
  const errorId = useId();
  const priceLabel = priceLabelFor(track);

  // The queue's `isPreviewPlaying` is the single source of truth, so
  // starting another row's preview stops this one through the same path a
  // click on this row's own button takes (FR-041: one preview at a time).
  // The audio is fetched by the browser straight from Apple's preview host,
  // never proxied through the backend (ADR 0021).
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!isPreviewPlaying) {
      audio.pause();
      return;
    }
    setPreviewError(null);
    // A rejected play() (autoplay policy, an unreachable preview host, a
    // withdrawn preview) must say so and release the control, never leave a
    // button reading "Pauzeer fragment" over silence.
    void Promise.resolve(audio.play()).catch(() => {
      setPreviewError("Fragment kon niet worden afgespeeld.");
      onPreviewChange(track.id, false);
    });
  }, [isPreviewPlaying, onPreviewChange, track.id]);

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

      {/* FR-041: hear it before buying it. The accessible name names the
          track (so a screen-reader user knows which row's preview this is)
          while the visible label stays short, and the playing/stopped state
          is carried by that label AND aria-pressed -- never by colour or an
          icon alone. */}
      <div className="flex flex-wrap items-center gap-8">
        {track.itunes_preview_url ? (
          <>
            <button
              type="button"
              aria-pressed={isPreviewPlaying}
              aria-label={`${isPreviewPlaying ? "Pauzeer" : "Speel"} fragment van ${track.artist} – ${track.title}`}
              onClick={() => onPreviewChange(track.id, !isPreviewPlaying)}
              className="min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
            >
              {isPreviewPlaying ? "Pauzeer fragment" : "Speel fragment"}
            </button>
            <audio
              ref={audioRef}
              src={track.itunes_preview_url}
              onPlay={() => onPreviewChange(track.id, true)}
              onPause={() => onPreviewChange(track.id, false)}
              onEnded={() => onPreviewChange(track.id, false)}
            />
          </>
        ) : (
          <p className="text-body-lg text-mist">Geen fragment beschikbaar.</p>
        )}
        {previewError && (
          <p role="alert" className="text-body-lg font-semibold text-pure-white">
            {previewError}
          </p>
        )}
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
          {/* FR-041: what it costs, beside the link that sells it. Absent
              for a track the store does not sell on its own, and then
              nothing is shown rather than a placeholder amount. */}
          {priceLabel && <span className="text-body-lg text-bone">Prijs: {priceLabel}</span>}
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
  // FR-041: at most one preview sounds at a time, so the id of the playing
  // row lives here rather than as per-row playing state -- starting one
  // preview is what stops the previous one.
  const [playingPreviewId, setPlayingPreviewId] = useState<number | null>(null);

  // Stable across renders, so the row effect that starts/stops the audio
  // element runs on a real state change instead of on every render.
  const handlePreviewChange = useCallback((id: number, playing: boolean) => {
    setPlayingPreviewId((current) => {
      if (playing) return id;
      // Only the row that is actually sounding may clear the field: a stop
      // arriving from the row that was just superseded must not silence the
      // one that superseded it.
      return current === id ? null : current;
    });
  }, []);

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
    // Switching view unmounts the playing row's audio element, so the
    // remembered id would otherwise outlive the sound it stands for.
    setPlayingPreviewId(null);
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
      {/* The panel title is the Koop-wachtrij view's own <h1> now, so this
          row carries only its action. */}
      <div className="flex items-center justify-end gap-16">
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
              isPreviewPlaying={playingPreviewId === track.id}
              onPreviewChange={handlePreviewChange}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
