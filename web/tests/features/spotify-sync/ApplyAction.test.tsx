// T051: confirmation dialog, result state, refusal/failure messages naming
// the blocking condition and the fix (FR-015..FR-019, WCAG).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { ApplyAction } from "../../../src/features/spotify-sync/ApplyAction";

vi.mock("../../../src/api/client", () => ({
  apiClient: { POST: vi.fn() },
}));

function mockApply(result: { data?: unknown; error?: unknown }) {
  vi.mocked(apiClient.POST).mockResolvedValue(result as never);
}

beforeEach(() => {
  // jsdom doesn't implement <dialog>'s native showModal()/close(); a
  // component relying on real modal behavior needs these stubbed.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderApplyAction(overrides = {}) {
  return render(<ApplyAction sessionId={1} defaultPlaylistName="Booking 2026" {...overrides} />);
}

describe("ApplyAction", () => {
  it("opens a confirmation dialog pre-filled with the session's name before applying", () => {
    renderApplyAction();

    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    expect(screen.getByDisplayValue("Booking 2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bevestig toepassen" })).toBeInTheDocument();
  });

  it("cancelling the dialog makes no request", () => {
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Annuleren" }));

    expect(apiClient.POST).not.toHaveBeenCalled();
  });

  it("confirming posts the (possibly edited) playlist name and shows the success result", async () => {
    mockApply({
      data: {
        rb_playlist_id: "rb-1",
        created: true,
        tracks_added: 3,
        tracks_already_present: 1,
        backup_path: "/data/backups/master-1.db.zip",
        readback_ok: true,
      },
      error: undefined,
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));
    fireEvent.change(screen.getByLabelText("Playlistnaam"), {
      target: { value: "Mijn Booking" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/apply",
        expect.objectContaining({
          params: { path: { session_id: 1 } },
          body: { playlist_name: "Mijn Booking" },
        }),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Playlist aangemaakt: 3 nummer(s) toegevoegd. Backup: /data/backups/master-1.db.zip.",
    );
  });

  it("shows an 'updated' message, distinct from 'created', when the Target Playlist already existed (FR-019)", async () => {
    mockApply({
      data: {
        rb_playlist_id: "rb-1",
        created: false,
        tracks_added: 2,
        tracks_already_present: 5,
        backup_path: "/data/backups/master-3.db.zip",
        readback_ok: true,
      },
      error: undefined,
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Playlist bijgewerkt: 2 nieuw, 5 al aanwezig. Backup: /data/backups/master-3.db.zip.",
    );
  });

  it("shows a 'created' message when the Target Playlist was deleted in Rekordbox and recreated (US3 scenario 5)", async () => {
    // writer.apply_playlist reports a recreated Target Playlist the same way
    // as a genuinely new one (`created: true`, a fresh rb_playlist_id) -- see
    // its docstring. The DJ still needs to see this differ from a plain
    // update, which this message does regardless of which case it was.
    mockApply({
      data: {
        rb_playlist_id: "rb-2",
        created: true,
        tracks_added: 1,
        tracks_already_present: 0,
        backup_path: "/data/backups/master-4.db.zip",
        readback_ok: true,
      },
      error: undefined,
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Playlist aangemaakt: 1 nummer(s) toegevoegd. Backup: /data/backups/master-4.db.zip.",
    );
  });

  it("sends undefined, not an empty string, when the playlist name is cleared", async () => {
    mockApply({
      data: {
        rb_playlist_id: "rb-1",
        created: true,
        tracks_added: 1,
        tracks_already_present: 0,
        backup_path: "/data/backups/master-1.db.zip",
        readback_ok: true,
      },
      error: undefined,
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));
    fireEvent.change(screen.getByLabelText("Playlistnaam"), { target: { value: "   " } });

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/apply",
        expect.objectContaining({ body: { playlist_name: undefined } }),
      ),
    );
  });

  it("tells the caller whether the applied write was verified", async () => {
    mockApply({
      data: {
        rb_playlist_id: "rb-1",
        created: true,
        tracks_added: 1,
        tracks_already_present: 0,
        backup_path: "/data/backups/master-1.db.zip",
        readback_ok: false,
      },
      error: undefined,
    });
    const onApplied = vi.fn();
    renderApplyAction({ onApplied });
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(false));
  });

  it("shows the backup path to restore when the write's own readback verification fails", async () => {
    mockApply({
      data: {
        rb_playlist_id: "rb-1",
        created: false,
        tracks_added: 2,
        tracks_already_present: 0,
        backup_path: "/data/backups/master-2.db.zip",
        readback_ok: false,
      },
      error: undefined,
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Herstel de Rekordbox-database vanaf de backup");
    expect(alert).toHaveTextContent("/data/backups/master-2.db.zip");
  });

  it.each([
    ["rekordbox_running", "Sluit Rekordbox af en probeer het opnieuw."],
    ["version_mismatch", "Controleer de installatie."],
    ["insufficient_disk", "Maak ruimte vrij en probeer het opnieuw."],
    ["backup_failed", "is er niets geschreven"],
  ])("names the blocking condition and the fix for %s", async (code, expectedSubstring) => {
    mockApply({ data: undefined, error: { code, message: "backend detail" } });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(expectedSubstring);
  });

  it("names both the found and required Rekordbox version for version_mismatch (US3 scenario 3)", async () => {
    mockApply({
      data: undefined,
      error: {
        code: "version_mismatch",
        message: "Installed Rekordbox version is 7.1.0, but 7.2.17 is required.",
      },
    });
    renderApplyAction();
    fireEvent.click(screen.getByRole("button", { name: "Toepassen op Rekordbox" }));

    fireEvent.click(screen.getByRole("button", { name: "Bevestig toepassen" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("7.1.0");
    expect(alert).toHaveTextContent("7.2.17");
  });
});
