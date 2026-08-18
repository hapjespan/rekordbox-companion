import { useId, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "./types";
import type { ApiError, SyncSession } from "./types";

interface PlaylistUrlFormProps {
  onSessionCreated: (session: SyncSession) => void;
  // The shell's "Sync" pill switches to the Match-overzicht view and focuses
  // this field (HANDOFF.md, "Top bar").
  inputRef?: React.Ref<HTMLInputElement>;
}

// T031: URL input starting a Sync Session, with field-naming validation
// errors for invalid/private/unreachable playlists (WCAG: an error names
// the field and the fix, spec.md's naming-input acceptance criterion).
export function PlaylistUrlForm({ onSessionCreated, inputRef }: PlaylistUrlFormProps) {
  const [playlistUrl, setPlaylistUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const inputId = useId();
  const errorId = useId();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const { data, error: apiError } = await apiClient.POST("/api/sync/sessions", {
      body: { playlist_url: playlistUrl },
    });

    setSubmitting(false);

    if (apiError) {
      setError(asApiResponse<ApiError>(apiError));
      return;
    }

    onSessionCreated(asApiResponse<SyncSession>(data));
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8" noValidate>
      <label htmlFor={inputId} className="text-body-lg font-semibold text-pure-white">
        Spotify-afspeellijst URL
      </label>
      <input
        id={inputId}
        ref={inputRef}
        type="text"
        inputMode="url"
        autoComplete="off"
        value={playlistUrl}
        onChange={(event) => setPlaylistUrl(event.target.value)}
        placeholder="https://open.spotify.com/playlist/..."
        aria-invalid={error !== null}
        aria-describedby={error ? errorId : undefined}
        className="min-h-24 rounded-full border border-iron bg-graphite px-12 py-8 text-body-lg text-pure-white placeholder-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      />
      {error && (
        <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
          Fout: {errorMessageFor(error)}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting || playlistUrl.trim() === ""}
        className="min-h-24 w-fit rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
      >
        {submitting ? "Bezig met synchroniseren…" : "Synchroniseren"}
      </button>
    </form>
  );
}

function errorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "missing_field":
      return "Vul een Spotify-afspeellijst URL in.";
    case "invalid_playlist_url":
      return "Dit is geen geldige Spotify-afspeellijst URL. Controleer de link en probeer het opnieuw.";
    case "playlist_too_large":
      return "Deze afspeellijst heeft meer dan 999 nummers. Splits de afspeellijst op en probeer het opnieuw.";
    case "spotify_not_connected":
      return "Verbind eerst je Spotify-account voordat je kunt synchroniseren.";
    case "playlist_unreachable":
      return "Deze afspeellijst is niet beschikbaar. Controleer of de afspeellijst openbaar is en dat de link klopt.";
    default:
      return (
        error.message ||
        "Er ging iets mis bij het ophalen van de afspeellijst. Probeer het opnieuw."
      );
  }
}
