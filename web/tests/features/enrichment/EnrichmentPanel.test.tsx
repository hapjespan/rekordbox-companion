// T077: coverage status, unenriched work list, manual genre editor with
// field-naming errors, manual/automatic origin conveyed in text (WCAG).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { EnrichmentPanel } from "../../../src/features/enrichment/EnrichmentPanel";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn() },
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] ?? []) {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

const STATUS = { pending: 5, done: 10, none_found: 2, failed: 0, coverage_pct: 71.4 };
const UNENRICHED_TRACK = { rb_content_id: "1", artist: "Obscure Artist", title: "B-Side" };

function mockGet(path: string, data: unknown) {
  vi.mocked(apiClient.GET).mockImplementation(((requestedPath: string) => {
    if (requestedPath === path) return Promise.resolve({ data, error: undefined });
    if (requestedPath === "/api/enrichment/status") {
      return Promise.resolve({ data: STATUS, error: undefined });
    }
    if (requestedPath === "/api/enrichment/unenriched") {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined });
    }
    return Promise.resolve({ data: undefined, error: undefined });
  }) as never);
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  mockGet("/api/enrichment/status", STATUS);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("EnrichmentPanel", () => {
  it("shows the coverage status fetched on mount", async () => {
    render(<EnrichmentPanel />);

    expect(await screen.findByText("71.4%")).toBeInTheDocument();
    expect(screen.getByText("10 verrijkt, 5 wachten, 2 niet gevonden")).toBeInTheDocument();
  });

  it("starts a run and disables the button while it is in progress", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { queued: 2 },
      error: undefined,
    } as never);
    render(<EnrichmentPanel />);
    await screen.findByText("71.4%");

    fireEvent.click(screen.getByRole("button", { name: "Verrijking starten" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith("/api/enrichment/run");
    });
    expect(screen.getByRole("button", { name: "Verrijking starten" })).toBeDisabled();
  });

  it("re-enables the start button and refreshes status when the run finishes (SSE)", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({ data: { queued: 1 }, error: undefined } as never);
    render(<EnrichmentPanel />);
    await screen.findByText("71.4%");
    fireEvent.click(screen.getByRole("button", { name: "Verrijking starten" }));
    await waitFor(() => expect(apiClient.POST).toHaveBeenCalled());

    const source = FakeEventSource.instances[0];
    source.emit("enrichment_progress", { done: 1, none_found: 0, failed: 0, remaining: 0 });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Verrijking starten" })).toBeEnabled();
    });
  });

  it("closes the SSE connection on unmount", async () => {
    const { unmount } = render(<EnrichmentPanel />);
    await screen.findByText("71.4%");

    unmount();

    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("lists unenriched tracks for the manual work list (FR-029)", async () => {
    mockGet("/api/enrichment/unenriched", { total: 1, items: [UNENRICHED_TRACK] });
    render(<EnrichmentPanel />);

    expect(await screen.findByText("Obscure Artist – B-Side")).toBeInTheDocument();
  });

  it("sets a manual genre override and labels it as manual, not automatic (WCAG)", async () => {
    mockGet("/api/enrichment/unenriched", { total: 1, items: [UNENRICHED_TRACK] });
    vi.mocked(apiClient.PUT).mockResolvedValue({
      data: { rb_content_id: "1", genres: [{ genre: "deep house", source: "manual" }] },
      error: undefined,
    } as never);
    render(<EnrichmentPanel />);
    await screen.findByText("Obscure Artist – B-Side");

    fireEvent.change(screen.getByLabelText("Genres (komma-gescheiden)"), {
      target: { value: "deep house" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    await waitFor(() => {
      expect(apiClient.PUT).toHaveBeenCalledWith("/api/collection/{rb_content_id}/genres", {
        params: { path: { rb_content_id: "1" } },
        body: { genres: ["deep house"] },
      });
    });
    expect(await screen.findByText("deep house (handmatig)")).toBeInTheDocument();
  });

  it("refetches the work list and status after a successful save, so a resolved track disappears", async () => {
    let unenrichedCallCount = 0;
    vi.mocked(apiClient.GET).mockImplementation((path: string) => {
      if (path === "/api/enrichment/status") {
        return Promise.resolve({ data: STATUS, error: undefined }) as never;
      }
      if (path === "/api/enrichment/unenriched") {
        unenrichedCallCount += 1;
        const items = unenrichedCallCount === 1 ? [UNENRICHED_TRACK] : [];
        return Promise.resolve({ data: { total: items.length, items }, error: undefined }) as never;
      }
      return Promise.resolve({ data: undefined, error: undefined }) as never;
    });
    vi.mocked(apiClient.PUT).mockResolvedValue({
      data: { rb_content_id: "1", genres: [{ genre: "deep house", source: "manual" }] },
      error: undefined,
    } as never);
    render(<EnrichmentPanel />);
    await screen.findByText("Obscure Artist – B-Side");

    fireEvent.change(screen.getByLabelText("Genres (komma-gescheiden)"), {
      target: { value: "deep house" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    await waitFor(() => {
      expect(screen.queryByText("Obscure Artist – B-Side")).not.toBeInTheDocument();
    });
    expect(unenrichedCallCount).toBeGreaterThanOrEqual(2);
  });

  it("shows a field-naming error and does not submit when no genre is entered", async () => {
    mockGet("/api/enrichment/unenriched", { total: 1, items: [UNENRICHED_TRACK] });
    render(<EnrichmentPanel />);
    await screen.findByText("Obscure Artist – B-Side");

    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    expect(await screen.findByText("Vul minstens één genre in.")).toBeInTheDocument();
    expect(apiClient.PUT).not.toHaveBeenCalled();
  });

  it("shows the backend error message when saving a manual genre fails", async () => {
    mockGet("/api/enrichment/unenriched", { total: 1, items: [UNENRICHED_TRACK] });
    vi.mocked(apiClient.PUT).mockResolvedValue({
      data: undefined,
      error: { code: "track_not_found", message: "no Collection Track with id '1'" },
    } as never);
    render(<EnrichmentPanel />);
    await screen.findByText("Obscure Artist – B-Side");

    fireEvent.change(screen.getByLabelText("Genres (komma-gescheiden)"), {
      target: { value: "house" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    expect(
      await screen.findByText("Dit nummer bestaat niet meer in de collectie."),
    ).toBeInTheDocument();
  });
});
