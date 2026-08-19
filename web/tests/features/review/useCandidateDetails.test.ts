// Resolving a review candidate's Rekordbox row by id, through
// GET /api/collection's `?ids=` filter: exact, one request per batch of at
// most 200 ids (the endpoint's own cap, `422 too_many_ids` above it), cached
// for the session, and degrading to "not in the collection" for an id the
// collection genuinely does not know.
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import {
  MAX_IDS_PER_REQUEST,
  useCandidateDetails,
} from "../../../src/features/review/useCandidateDetails";
import type { CandidateLookupItem } from "../../../src/features/review/useCandidateDetails";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

function itemsFor(ids: string[]): CandidateLookupItem[] {
  return [{ candidates: ids.map((id) => ({ rb_content_id: id })) }];
}

function row(id: string, overrides: Record<string, unknown> = {}) {
  return {
    rb_content_id: id,
    artist: `Artiest ${id}`,
    title: `Titel ${id}`,
    duration_ms: 300_000,
    bpm: null,
    musical_key: null,
    label: null,
    ...overrides,
  };
}

// Answers with a row for every id the caller asked for, the way the endpoint
// does (unknown ids are simply absent, which the tests below drive explicitly).
function mockCollection(known: Set<string> | null = null) {
  vi.mocked(apiClient.GET).mockImplementation(((
    _path: string,
    options?: { params?: { query?: { ids?: string[] } } },
  ) => {
    const ids = options?.params?.query?.ids ?? [];
    const items = ids.filter((id) => known === null || known.has(id)).map((id) => row(id));
    return Promise.resolve({ data: { total: items.length, items }, error: undefined });
  }) as never);
}

function idsOfCall(index: number): string[] {
  const call = vi.mocked(apiClient.GET).mock.calls[index] as unknown as [
    string,
    { params: { query: { ids: string[]; limit: number } } },
  ];
  return call[1].params.query.ids;
}

beforeEach(() => {
  vi.mocked(apiClient.GET).mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCandidateDetails", () => {
  it("asks for every candidate of the whole queue by id, in one request", async () => {
    mockCollection();

    const { result } = renderHook(() => useCandidateDetails(itemsFor(["rb-a", "rb-b", "rb-c"])));

    await waitFor(() => expect(result.current.size).toBe(3));
    expect(apiClient.GET).toHaveBeenCalledTimes(1);
    expect(apiClient.GET).toHaveBeenCalledWith("/api/collection", {
      params: { query: { ids: ["rb-a", "rb-b", "rb-c"], limit: MAX_IDS_PER_REQUEST } },
    });
    expect(result.current.get("rb-b")).toMatchObject({ title: "Titel rb-b", bpm: null });
  });

  it("never sends more ids than the endpoint accepts, batching the rest", async () => {
    const ids = Array.from({ length: MAX_IDS_PER_REQUEST + 5 }, (_, index) => `rb-${index}`);
    mockCollection();

    const { result } = renderHook(() => useCandidateDetails(itemsFor(ids)));

    await waitFor(() => expect(result.current.size).toBe(ids.length));
    expect(apiClient.GET).toHaveBeenCalledTimes(2);
    expect(idsOfCall(0)).toHaveLength(MAX_IDS_PER_REQUEST);
    expect(idsOfCall(1)).toEqual(ids.slice(MAX_IDS_PER_REQUEST));
  });

  it("asks a second time only for ids it has no answer for yet", async () => {
    mockCollection(new Set(["rb-a"]));

    const { result, rerender } = renderHook(
      ({ ids }: { ids: string[] }) => useCandidateDetails(itemsFor(ids)),
      { initialProps: { ids: ["rb-a", "rb-unknown"] } },
    );
    await waitFor(() => expect(result.current.size).toBe(1));

    rerender({ ids: ["rb-a", "rb-unknown", "rb-new"] });

    await waitFor(() => expect(apiClient.GET).toHaveBeenCalledTimes(2));
    // Neither the row already cached nor the id the collection answered it
    // does not have is asked for again.
    expect(idsOfCall(1)).toEqual(["rb-new"]);
  });

  it("resolves nothing and stays usable when the request fails, without retrying on its own", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("offline") as never);

    const { result, rerender } = renderHook(
      ({ ids }: { ids: string[] }) => useCandidateDetails(itemsFor(ids)),
      { initialProps: { ids: ["rb-a"] } },
    );

    await waitFor(() => expect(apiClient.GET).toHaveBeenCalledTimes(1));
    expect(result.current.size).toBe(0);

    // A failed batch is never marked "answered", so it stays pending -- but
    // nothing here re-runs the effect on its own (no new id, no state
    // change), so a same-ids rerender must not fire a second request.
    rerender({ ids: ["rb-a"] });
    expect(apiClient.GET).toHaveBeenCalledTimes(1);
  });

  it("makes no request at all for a queue without candidates", () => {
    mockCollection();

    renderHook(() => useCandidateDetails([{ candidates: [] }]));

    expect(apiClient.GET).not.toHaveBeenCalled();
  });
});
