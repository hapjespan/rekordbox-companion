// Resolving a phase's rb_content_ids to BPM/key/duration without a per-id
// endpoint: a paged sweep over GET /api/collection that stops as early as it
// can, caches what it saw, and reports what it never found instead of
// inventing values for it.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import {
  COLLECTION_PAGE_SIZE,
  MAX_COLLECTION_PAGES,
  resolveTrackFacts,
} from "../../../src/features/bookings/collectionFacts";
import type { TrackFacts } from "../../../src/features/bookings/phaseModel";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
}));

function row(id: string, bpm: number | null = null, key: string | null = null) {
  return { rb_content_id: id, bpm, musical_key: key, duration_ms: 300_000 };
}

function mockPages(pages: { total: number; items: ReturnType<typeof row>[] }[]) {
  let call = 0;
  vi.mocked(apiClient.GET).mockImplementation((() => {
    const page = pages[Math.min(call, pages.length - 1)];
    call += 1;
    return Promise.resolve({ data: page, error: undefined });
  }) as never);
}

beforeEach(() => {
  vi.mocked(apiClient.GET).mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolveTrackFacts", () => {
  it("asks for one bounded page, never the whole collection in one request", async () => {
    mockPages([{ total: 119, items: [row("a", 124, "8m")] }]);

    const { facts } = await resolveTrackFacts(["a"], new Map());

    expect(apiClient.GET).toHaveBeenCalledWith("/api/collection", {
      params: { query: { limit: COLLECTION_PAGE_SIZE, offset: 0 } },
    });
    expect(apiClient.GET).toHaveBeenCalledTimes(1);
    expect(facts.get("a")).toEqual({ bpm: 124, musical_key: "8m", duration_ms: 300_000 });
  });

  it("keeps paging while an id is still missing, and stops the moment it is found", async () => {
    mockPages([
      { total: 400, items: [row("a")] },
      { total: 400, items: [row("b", 130, "2d")] },
      { total: 400, items: [row("c")] },
    ]);

    const { facts, unresolved } = await resolveTrackFacts(["b"], new Map());

    expect(apiClient.GET).toHaveBeenCalledTimes(2);
    expect(facts.get("b")?.bpm).toBe(130);
    expect(unresolved).toEqual([]);
  });

  it("gives up after a bounded number of pages and reports what stayed unknown", async () => {
    mockPages([{ total: 40_000, items: [row("filler")] }]);

    const { unresolved } = await resolveTrackFacts(["nowhere"], new Map());

    expect(apiClient.GET).toHaveBeenCalledTimes(MAX_COLLECTION_PAGES);
    expect(unresolved).toEqual(["nowhere"]);
  });

  it("costs nothing for ids the cache already holds", async () => {
    const cache = new Map<string, TrackFacts>([
      ["a", { bpm: 124, musical_key: "8m", duration_ms: 1000 }],
    ]);

    const { unresolved } = await resolveTrackFacts(["a"], cache);

    expect(apiClient.GET).not.toHaveBeenCalled();
    expect(unresolved).toEqual([]);
  });

  it("degrades to unknown when the collection request fails", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("offline") as never);

    const { facts, unresolved } = await resolveTrackFacts(["a"], new Map());

    expect(facts.has("a")).toBe(false);
    expect(unresolved).toEqual(["a"]);
  });
});
