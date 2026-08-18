// T065 (FR-025/FR-026, WCAG): progress bar + seek only, playing/paused/seek
// state exposed to assistive tech; a missing file is reported by name.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerBar } from "../../src/components/PlayerBar";

const TRACK = { rb_content_id: "rb1", artist: "Daft Punk", title: "One More Time" };

beforeEach(() => {
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PlayerBar", () => {
  it("renders nothing when no track is selected", () => {
    const { container } = render(<PlayerBar track={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the track and a status region reflecting play/pause", () => {
    render(<PlayerBar track={TRACK} />);

    expect(screen.getByText("Daft Punk – One More Time")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Gepauzeerd");
  });

  it("toggling play calls audio.play() and updates the button/status on the native play event", () => {
    const { container } = render(<PlayerBar track={TRACK} />);

    fireEvent.click(screen.getByRole("button", { name: "Afspelen" }));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);

    const audio = container.querySelector("audio") as HTMLAudioElement;
    fireEvent.play(audio);

    expect(screen.getByRole("button", { name: "Pauzeer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Speelt af");
  });

  it("seeking updates audio.currentTime", () => {
    const { container } = render(<PlayerBar track={TRACK} />);
    const audio = container.querySelector("audio") as HTMLAudioElement;
    Object.defineProperty(audio, "duration", { value: 210, configurable: true });
    fireEvent.loadedMetadata(audio);

    const seekInput = screen.getByRole("slider");
    fireEvent.change(seekInput, { target: { value: "60" } });

    expect(audio.currentTime).toBe(60);
  });

  it("reports a missing audio file by name, not a silent or generic failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ code: "file_missing", message: "gone" }),
      }),
    );
    const { container } = render(<PlayerBar track={TRACK} />);
    const audio = container.querySelector("audio") as HTMLAudioElement;

    fireEvent.error(audio);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Audiobestand ontbreekt op schijf.");
    expect(screen.getByRole("button", { name: "Afspelen" })).toBeDisabled();
    vi.unstubAllGlobals();
  });

  it("resets playback state when a different track is selected", () => {
    const { rerender } = render(<PlayerBar track={TRACK} />);
    fireEvent.click(screen.getByRole("button", { name: "Afspelen" }));

    const otherTrack = { rb_content_id: "rb2", artist: "Adele", title: "Rolling in the Deep" };
    rerender(<PlayerBar track={otherTrack} />);

    expect(screen.getByText("Adele – Rolling in the Deep")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Gepauzeerd");
  });
});
