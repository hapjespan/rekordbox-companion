import { useId, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "./types";
import type { ApiError } from "./types";

interface ApplyResult {
  rb_playlist_id: string;
  created: boolean;
  tracks_added: number;
  tracks_already_present: number;
  backup_path: string;
  readback_ok: boolean;
}

interface ApplyActionProps {
  sessionId: number;
  defaultPlaylistName: string;
  // `verified` is false for a readback failure (spec.md US3 scenario 7):
  // the write and its backup are real, but NOT confirmed and NOT marked
  // applied, so a caller must not treat this the same as a clean success.
  onApplied?: (verified: boolean) => void;
}

// A discriminated union instead of separate phase/result/error state: a
// state like "success" with a null result becomes unrepresentable, rather
// than merely unlikely (review finding).
type ApplyState =
  | { status: "idle" | "applying" }
  | { status: "success" | "readback_failed"; result: ApplyResult }
  | { status: "refused"; error: ApiError };

// T051 (FR-015..FR-019, WCAG): a confirmation dialog before writing to the
// DJ's real Rekordbox library, then a result state that always names what
// happened -- success, a pre-write refusal naming the blocking condition
// and the fix, or a post-write readback failure naming the backup to
// restore (spec.md US3 scenario 7, distinct from a refusal: the write and
// its backup are real, only verification didn't confirm it).
export function ApplyAction({ sessionId, defaultPlaylistName, onApplied }: ApplyActionProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [playlistName, setPlaylistName] = useState(defaultPlaylistName);
  const [state, setState] = useState<ApplyState>({ status: "idle" });
  const nameInputId = useId();

  function openConfirm() {
    setPlaylistName(defaultPlaylistName);
    dialogRef.current?.showModal();
  }

  async function handleConfirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ status: "applying" });

    const { data, error: apiError } = await apiClient.POST(
      "/api/sync/sessions/{session_id}/apply",
      {
        params: { path: { session_id: sessionId } },
        body: { playlist_name: playlistName.trim() || undefined },
      },
    );

    dialogRef.current?.close();

    if (apiError) {
      setState({ status: "refused", error: asApiResponse<ApiError>(apiError) });
      return;
    }

    const result = asApiResponse<ApplyResult>(data);
    setState({ status: result.readback_ok ? "success" : "readback_failed", result });
    onApplied?.(result.readback_ok);
  }

  return (
    <div className="flex flex-col gap-12">
      <button
        type="button"
        onClick={openConfirm}
        disabled={state.status === "applying"}
        className="min-h-24 w-fit rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
      >
        Toepassen op Rekordbox
      </button>

      <dialog
        ref={dialogRef}
        className="rounded-md border border-iron bg-graphite p-24 text-pure-white backdrop:bg-void-black/70"
      >
        <form onSubmit={handleConfirm} className="flex flex-col gap-16">
          {/* B9: the dialog's own heading, not a styled paragraph. */}
          <h2 className="text-body-lg font-bold">Toepassen op Rekordbox</h2>
          <p className="text-body-lg text-mist">
            Dit schrijft de geaccepteerde, gematchte nummers als playlist naar Rekordbox, na een
            backup.
          </p>
          <label htmlFor={nameInputId} className="text-body-lg font-semibold">
            Playlistnaam
          </label>
          <input
            id={nameInputId}
            type="text"
            value={playlistName}
            onChange={(event) => setPlaylistName(event.target.value)}
            className="min-h-24 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          />
          <div className="flex gap-12">
            <button
              type="submit"
              disabled={state.status === "applying"}
              className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
            >
              {state.status === "applying" ? "Bezig met toepassen…" : "Bevestig toepassen"}
            </button>
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              disabled={state.status === "applying"}
              className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
            >
              Annuleren
            </button>
          </div>
        </form>
      </dialog>

      {state.status === "success" && (
        <p role="status" className="text-body-lg text-pure-white">
          {successMessageFor(state.result)}
        </p>
      )}

      {state.status === "readback_failed" && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          Schrijven gelukt, maar verificatie is mislukt. Herstel de Rekordbox-database vanaf de
          backup: {state.result.backup_path}.
        </p>
      )}

      {state.status === "refused" && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          Niet toegepast: {refusalMessageFor(state.error)}
        </p>
      )}
    </div>
  );
}

// FR-019/US3 scenario 5: a Target Playlist deleted inside Rekordbox since the
// last apply is detected and recreated, and the DJ must be told -- a
// recreated playlist is a NEW Rekordbox id under `writer.apply_playlist`'s
// own create-vs-reuse rule, so `result.created` is exactly the signal this
// needs. Without this, "created" and "reused-and-updated" read identically.
function successMessageFor(result: ApplyResult): string {
  if (result.created) {
    return `Playlist aangemaakt: ${result.tracks_added} nummer(s) toegevoegd. Backup: ${result.backup_path}.`;
  }
  return `Playlist bijgewerkt: ${result.tracks_added} nieuw, ${result.tracks_already_present} al aanwezig. Backup: ${result.backup_path}.`;
}

function refusalMessageFor(error: ApiError): string {
  switch (error.code) {
    case "rekordbox_running":
      return "Rekordbox staat open. Sluit Rekordbox af en probeer het opnieuw.";
    case "version_mismatch":
      // spec.md US3 scenario 3: the message must name both the found and
      // the required version. guard.py's message already carries both
      // dynamically (e.g. "Installed Rekordbox version is 7.1.0, but
      // 7.2.17 is required.") -- ApiError has no structured found-version
      // field, so it's appended as supporting detail rather than dropped
      // (same fallback-to-backend-text precedent as the default branch
      // below and PlaylistUrlForm's errorMessageFor).
      return `De geïnstalleerde Rekordbox-versie komt niet overeen met de vereiste versie. Controleer de installatie. (${error.message})`;
    case "insufficient_disk":
      return "Onvoldoende vrije schijfruimte voor een backup. Maak ruimte vrij en probeer het opnieuw.";
    case "backup_failed":
      return "De backup kon niet worden geverifieerd, dus is er niets geschreven. Probeer het opnieuw.";
    default:
      return error.message || "Er ging iets mis bij het toepassen. Probeer het opnieuw.";
  }
}
