import { useId } from "react";

import { MATCH_FILTER_CHIPS, MATCH_SORT_OPTIONS } from "./matchFilters";
import type { MatchFilter, MatchSort } from "./matchFilters";

interface MatchFiltersProps {
  filter: MatchFilter;
  onFilterChange: (filter: MatchFilter) => void;
  sort: MatchSort;
  onSortChange: (sort: MatchSort) => void;
}

// The prototype's filter row: chips 30px high, 14px horizontal padding, fully
// rounded, 12px/700, the selected one white-on-black and the rest graphite
// with a smoke hover, and the sort control right-aligned in muted 12px.
//
// Every chip is a toggle button carrying `aria-pressed`, so the selected
// filter is exposed programmatically and not by the white fill alone, and is
// 30px tall (>= WCAG 2.2's 24x24 target minimum). The sort control is a real
// <select> with a visible <label>, not the design's static caption.
export function MatchFilters({ filter, onFilterChange, sort, onSortChange }: MatchFiltersProps) {
  const sortId = useId();

  return (
    <div className="flex flex-wrap items-center gap-8">
      {MATCH_FILTER_CHIPS.map((chip) => {
        const selected = chip.value === filter;
        return (
          <button
            key={chip.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onFilterChange(chip.value)}
            className={`inline-flex h-30 min-w-24 items-center justify-center rounded-full-2 px-14 text-body-sm font-bold whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green ${
              selected
                ? "bg-pure-white text-void-black"
                : "bg-graphite text-pure-white hover:bg-smoke"
            }`}
          >
            {chip.label}
          </button>
        );
      })}
      <div className="flex-1" />
      <label htmlFor={sortId} className="text-body-sm text-mist">
        Sorteer op
      </label>
      <select
        id={sortId}
        value={sort}
        onChange={(event) => onSortChange(event.target.value as MatchSort)}
        className="h-30 rounded-full bg-graphite px-12 text-body-sm text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      >
        {MATCH_SORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
