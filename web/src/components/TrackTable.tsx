import { useEffect, useId, useRef, useState } from "react";

import { apiClient } from "../api/client";
import { asApiResponse } from "../features/spotify-sync/types";

export interface CollectionTrackDto {
  rb_content_id: string;
  artist: string;
  title: string;
  duration_ms: number | null;
  bpm: number | null;
  play_count: number;
  genres: { genre: string; source: string }[];
  format: string | null;
}

type SortField = "artist" | "title" | "bpm" | "play_count";

const COLUMNS: { field: SortField; label: string }[] = [
  { field: "artist", label: "Artiest" },
  { field: "title", label: "Titel" },
  { field: "bpm", label: "BPM" },
  { field: "play_count", label: "Afspeelteller" },
];

const PAGE_SIZE = 50;

// Review finding (FR-026's silent-failure ban, already applied to the
// player): an API error shaped `{code, message}` (contracts/api.md) must
// not collapse into the same "total=0, tracks=[]" the table also gets for a
// genuinely empty result -- those are different states and need different
// Dutch copy, not one generic-looking empty table either way.
interface ApiErrorBody {
  code?: string;
  message?: string;
}

function errorMessageFor(apiError: unknown): string {
  const body = apiError as ApiErrorBody | undefined;
  if (body?.code === "rekordbox_not_found") {
    return "Rekordbox is niet gevonden. Start Rekordbox en herlaad de pagina.";
  }
  return "Kon de collectie niet laden. Probeer het opnieuw.";
}

interface TrackTableProps {
  onPlay?: (track: CollectionTrackDto) => void;
  // The shell's top-bar search seeds this table's query (HANDOFF.md, "Top
  // bar"); the token makes searching the same term twice re-seed the field.
  seedQuery?: string;
  seedToken?: number;
  // Bumped by the sidebar's Collectie-scan card once a rebuild completes, so
  // the table shows the freshly indexed collection.
  reloadToken?: number;
}

// T064 (FR-024, WCAG): a searchable, sortable table over GET /api/collection.
// Review finding: a plain <table> with one tab stop per row (as MatchReport,
// T032, uses) is right for a READ-ONLY report but not for this actively
// browsable, playable table -- tabbing past up to 50 rows to reach a distant
// one is exactly the "keyboard navigation" gap the task text calls out
// separately from "searchable, sortable". Row actions use a roving-tabindex
// pattern instead (one row's Afspelen button is tab-reachable at a time;
// ArrowUp/ArrowDown move the active row without re-tabbing), the same
// technique ReviewQueue.tsx (T039) uses for its own composite widget --
// while keeping a real <table> (not a listbox) so screen-reader table
// semantics (row/column headers, cell relationships) stay intact.
// Paginates via the API's own limit/offset rather than rendering all 30k+
// rows at once (dense-layout AA contrast is a token/CSS concern, not a
// reason to virtualize for this proof-of-value cut, plan.md).
export function TrackTable({
  onPlay,
  seedQuery = "",
  seedToken = 0,
  reloadToken = 0,
}: TrackTableProps) {
  const [query, setQuery] = useState(seedQuery);
  const [sort, setSort] = useState<SortField>("artist");
  const [descending, setDescending] = useState(false);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [tracks, setTracks] = useState<CollectionTrackDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [activeRowIndex, setActiveRowIndex] = useState(0);
  const rowButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const searchInputId = useId();

  useEffect(() => {
    setActiveRowIndex(0);
  }, [tracks]);

  // A search submitted in the shell's top bar lands here.
  useEffect(() => {
    if (seedToken === 0) return;
    setQuery(seedQuery);
    setPage(0);
  }, [seedQuery, seedToken]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data, error: apiError } = await apiClient.GET("/api/collection", {
          params: {
            query: {
              query: query || undefined,
              sort: descending ? `-${sort}` : sort,
              limit: PAGE_SIZE,
              offset: page * PAGE_SIZE,
            },
          },
        });
        if (cancelled) return;
        if (apiError) {
          setError(errorMessageFor(apiError));
          setTotal(0);
          setTracks([]);
          return;
        }
        const body = asApiResponse<{ total: number; items: CollectionTrackDto[] } | undefined>(
          data,
        );
        setError(null);
        setTotal(body?.total ?? 0);
        setTracks(body?.items ?? []);
      } catch {
        if (!cancelled) {
          setError(errorMessageFor(undefined));
          setTotal(0);
          setTracks([]);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [query, sort, descending, page, reloadToken]);

  function handleSort(field: SortField) {
    if (field === sort) {
      setDescending((current) => !current);
    } else {
      setSort(field);
      setDescending(false);
    }
    setPage(0);
  }

  function handleQueryChange(value: string) {
    setQuery(value);
    setPage(0);
  }

  function handleRowKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const nextIndex =
      event.key === "ArrowDown" ? Math.min(index + 1, tracks.length - 1) : Math.max(index - 1, 0);
    setActiveRowIndex(nextIndex);
    rowButtonRefs.current[nextIndex]?.focus();
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-16">
      {/* The title is the Collection view's own <h1> now, and the rebuild
          control is the sidebar's Collectie-scan card (the delivered design
          puts it there); this panel is the table itself. */}
      <div className="flex flex-col gap-8">
        <label htmlFor={searchInputId} className="text-body-lg font-semibold text-pure-white">
          Zoeken in collectie
        </label>
        <input
          id={searchInputId}
          type="text"
          value={query}
          onChange={(event) => handleQueryChange(event.target.value)}
          placeholder="Artiest of titel..."
          className="min-h-24 rounded-full border border-iron bg-graphite px-12 py-8 text-body-lg text-pure-white placeholder-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-body-lg text-pure-white">
          <caption className="sr-only">Collectie, {total} nummers</caption>
          <thead>
            <tr>
              {COLUMNS.map(({ field, label }) => {
                const isActive = sort === field;
                return (
                  <th
                    key={field}
                    scope="col"
                    aria-sort={isActive ? (descending ? "descending" : "ascending") : "none"}
                    className="px-8 py-8 text-left"
                  >
                    <button
                      type="button"
                      onClick={() => handleSort(field)}
                      className="min-h-24 font-bold text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
                    >
                      {label}
                      {isActive ? (descending ? " ▼" : " ▲") : ""}
                    </button>
                  </th>
                );
              })}
              <th scope="col" className="px-8 py-8 text-left text-mist">
                Afspelen
              </th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((track, index) => (
              <tr key={track.rb_content_id} className="border-t border-iron">
                <td className="px-8 py-8">{track.artist}</td>
                <td className="px-8 py-8">{track.title}</td>
                <td className="px-8 py-8">{track.bpm ?? "–"}</td>
                <td className="px-8 py-8">{track.play_count}</td>
                <td className="px-8 py-8">
                  <button
                    ref={(el) => {
                      rowButtonRefs.current[index] = el;
                    }}
                    type="button"
                    tabIndex={index === activeRowIndex ? 0 : -1}
                    onFocus={() => setActiveRowIndex(index)}
                    onKeyDown={(event) => handleRowKeyDown(event, index)}
                    onClick={() => onPlay?.(track)}
                    className="min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
                  >
                    Afspelen
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
      {/* An empty index and an empty search result need different copy: the
          first is fixed by a scan, the second by a different search term. */}
      {!error && tracks.length === 0 && (
        <p className="text-body-lg text-mist">
          {query
            ? "Geen nummers gevonden."
            : "De collectie is nog niet ingelezen. Kies Opnieuw scannen in de kaart Collectie-scan links onderin om hem uit Rekordbox te lezen."}
        </p>
      )}

      <div className="flex items-center gap-16">
        <button
          type="button"
          onClick={() => setPage((current) => Math.max(0, current - 1))}
          disabled={page === 0}
          className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
        >
          Vorige
        </button>
        <p className="text-body-lg text-mist">
          Pagina {page + 1} van {pageCount} ({total} nummers)
        </p>
        <button
          type="button"
          onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
          disabled={page + 1 >= pageCount}
          className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
        >
          Volgende
        </button>
      </div>
    </div>
  );
}
