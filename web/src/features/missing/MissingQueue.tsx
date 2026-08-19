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

// FR-042: on macOS, swapping the `https` scheme for `itmss` on the same
// music.apple.com/itunes.apple.com URL hands that store page to the Music
// application instead of the browser -- the browser only offers excerpts of
// what the Music app plays and sells in full. Only rewritten when the URL
// actually is an `https` URL on one of those two hosts: `effective_url` can
// be the DJ's own pasted override (a free-text field, FR-020), which could
// point anywhere, and turning an arbitrary host into `itmss://` would
// produce a link that silently does nothing.
//
// This cannot be verified anywhere but a Mac: this container has no Music
// application to open the link in. The scheme swap itself is confirmed
// against Apple's own documentation for `itmss`, the iTunes Music Store
// Secure scheme; the Dutch UI copy below spells out that this is the app
// destination so the two links never look interchangeable.
function musicAppUrl(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (parsed.hostname !== "music.apple.com" && parsed.hostname !== "itunes.apple.com") {
    return null;
  }
  return `itmss:${url.slice("https:".length)}`;
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

interface QueueTotals {
  count: number;
  noPriceCount: number;
  totalLabel: string | null;
}

// HANDOFF.md's store-card header total and "Overzicht" summary panel both
// need the same arithmetic: sum only the prices that are actually present
// (FR-041 -- a streaming-only or album-only track has none) and report how
// many rows carry no price rather than quietly excluding them from the
// count the DJ sees.
function summarize(tracks: MissingTrackDto[]): QueueTotals {
  const priced = tracks.filter(
    (track): track is MissingTrackDto & { itunes_price: number } => track.itunes_price !== null,
  );
  let totalLabel: string | null = null;
  if (priced.length > 0) {
    const amount = priced.reduce((sum, track) => sum + track.itunes_price, 0);
    // Every row observed in practice prices in EUR (the iTunes NL
    // storefront); a genuinely mixed-currency queue is outside this cut's
    // scope, so the first present currency stands in for the summed total
    // rather than adding real multi-currency arithmetic.
    const currency = priced[0].itunes_currency ?? "EUR";
    try {
      totalLabel = new Intl.NumberFormat("nl-NL", { style: "currency", currency }).format(amount);
    } catch {
      totalLabel = `${amount.toFixed(2)} ${currency}`;
    }
  }
  return { count: tracks.length, noPriceCount: tracks.length - priced.length, totalLabel };
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
  const musicAppHref = track.effective_url ? musicAppUrl(track.effective_url) : null;

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
    <li data-testid="missing-track-row" className="flex flex-col gap-8 px-16 py-10 hover:bg-smoke">
      {/* HANDOFF.md's item row is a grid `22px minmax(0,1fr) 90px 70px 80px`
          (checkbox / track / bpm·key / quality / price). A Missing Track
          carries an Apple Music / iTunes link and a status, nothing else
          (FR-020..FR-022, ADR 0006) -- there is no bpm/key (that is
          Rekordbox collection data, not this row's) and no quality field,
          so both middle columns are dropped rather than filled with
          invented data. There is also no per-row checkout selection (no
          checkout button, owner decision), so the checkbox is repurposed as
          a decorative, aria-hidden echo of whether this row's price is one
          of the ones the summary panel's total actually counts; the same
          fact is already stated in text below (this row's own "Prijs: ..."
          line, or its absence), which is what a screen reader announces. */}
      <div className="grid grid-cols-[var(--spacing-22)_minmax(0,1fr)_var(--spacing-80)] items-center gap-16">
        <span
          aria-hidden="true"
          className={`flex h-15 w-15 flex-none items-center justify-center rounded-sm text-micro font-bold ${
            priceLabel ? "bg-spotify-green text-void-black" : "border border-iron"
          }`}
        >
          {priceLabel ? "✓" : null}
        </span>
        <p className="truncate text-body-lg font-semibold">
          {track.artist} – {track.title}
        </p>
        <span aria-hidden="true" className="text-right text-body font-semibold text-pure-white">
          {priceLabel ?? "–"}
        </span>
      </div>
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
          {/* FR-042: the Music app is the primary destination, because the
              app "ultimately runs on the DJ's Mac" -- the browser link stays
              as a fallback for machines with no Music application (this
              container included), and never disappears just because the
              scheme swap succeeded. The two link texts name their own
              destination outright, so the difference reads without a
              tooltip. */}
          {musicAppHref && (
            <a
              href={musicAppHref}
              className="text-body-lg text-spotify-green underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
            >
              Open in Muziek-app
            </a>
          )}
          <a
            href={track.effective_url}
            target="_blank"
            rel="noreferrer"
            className="text-body-lg text-bone underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            Open in browser
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
  // The summary panel's total is always the OPEN queue's, independent of
  // which status filter is currently shown in the store card (owner
  // decision: "the real total of the open tracks"). Kept as its own piece
  // of state rather than re-fetched on every filter switch: `refresh` below
  // already fetches "open" on first load (the default filter), so this
  // stays in step with zero extra requests whenever the DJ is looking at
  // the default view, and simply keeps the last known open total while
  // browsing Aangeschaft/Genegeerd.
  const [openTracks, setOpenTracks] = useState<MissingTrackDto[] | null>(null);
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
      const list = asApiResponse<MissingTrackDto[]>(data) ?? [];
      setTracks(list);
      if (status === "open") setOpenTracks(list);
    } catch {
      setTracks((current) => current ?? []);
      if (status === "open") setOpenTracks((current) => current ?? []);
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

  const cardTotals = summarize(tracks);
  const summaryTotals = summarize(openTracks ?? []);

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

      {/* HANDOFF.md's two-column buy-queue shell: one store card (left) and a
          sticky summary panel (right), stacking below the width the handoff
          names. That width is the `--breakpoint-stack` token, so the same
          number cannot drift apart between this view and the builder's grid. */}
      <div
        data-testid="buy-queue-columns"
        className="grid grid-cols-1 items-start gap-24 stack:grid-cols-[minmax(0,1fr)_minmax(var(--spacing-240),var(--spacing-300))]"
      >
        {/* Store card: HANDOFF.md shows one card per store (Beatport,
            Bandcamp, Traxsource); this app only ever resolves one store's
            link (Apple Music / iTunes, FR-020..FR-022/ADR 0006), so there is
            no per-store grouping beyond this single card -- it holds every
            row the current filter shows. */}
        <div data-testid="buy-queue-store-card" className="overflow-hidden rounded-md bg-graphite">
          <div className="flex items-center gap-8 border-b border-smoke px-16 py-14">
            <span className="text-body-lg font-bold text-pure-white">Apple Music</span>
            <span className="rounded-full-2 bg-smoke px-10 py-3 text-caption text-mist">
              {cardTotals.count} tracks
            </span>
            <span className="flex-1" />
            <span
              data-testid="buy-queue-store-card-total"
              className="text-body font-bold text-pure-white"
            >
              {cardTotals.totalLabel ?? "–"}
            </span>
          </div>

          {tracks.length === 0 ? (
            <p className="px-16 py-16 text-body-lg text-mist">{EMPTY_STATE_LABELS[statusFilter]}</p>
          ) : (
            <ul className="divide-y divide-smoke">
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

        {/* Summary panel: HANDOFF.md's "Overzicht" card. Its total always
            covers the open queue (see the `openTracks` comment above), and
            is computed only from the prices that are actually present
            (FR-041) -- the "zonder prijs" row says how many rows carry no
            price rather than quietly excluding them from what the DJ reads
            as "the total".
            Not built, because the app never handles money or a cart, and
            there is no watch-folder import: the "Afrekenen per winkel"
            checkout pill (owner decision) and the "Na aankoop" watch-folder
            card (FR-023, ADR 0008) that HANDOFF.md places here. */}
        <div
          data-testid="buy-queue-summary"
          className="sticky top-0 flex flex-col gap-14 rounded-md bg-graphite p-16"
        >
          <p className="text-body-lg font-bold text-pure-white">Overzicht</p>
          <div className="flex items-center justify-between text-body text-mist">
            <span>{summaryTotals.count} tracks</span>
            <span className="text-pure-white">{summaryTotals.totalLabel ?? "–"}</span>
          </div>
          <div className="flex items-center justify-between text-body text-mist">
            <span>{summaryTotals.noPriceCount} zonder prijs</span>
            <span>niet meegeteld</span>
          </div>
          <div className="flex items-center justify-between border-t border-iron pt-8 text-body-lg font-bold text-pure-white">
            <span>Totaal</span>
            <span>{summaryTotals.totalLabel ?? "–"}</span>
          </div>
          {/* theme.css deliberately does not use --color-fog for small text
              (it fails AA on these surfaces, ADR 0020); the footnote uses
              mist, the next step up, instead of the fog HANDOFF.md's
              prototype used. */}
          <p className="text-caption leading-body text-mist">
            Koop een nummer via de link op de rij; prijs en fragment komen van de Apple Music /
            iTunes Store.
          </p>
        </div>
      </div>
    </div>
  );
}
