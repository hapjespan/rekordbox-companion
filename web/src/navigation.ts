// The shell's view switcher (web/design-input/HANDOFF.md, "Sidebar").
//
// The delivered prototype has three views (match, buy, build). Three of the
// seven built user stories have no view there, and dropping them would make
// them unreachable -- which is exactly the failure the phase 7 review caught
// twice (see App.tsx). So the WORKSPACE list carries five items: the
// prototype's three plus the Collection browser (US5) and Genre enrichment
// (US6).
export type ViewId = "match" | "buy" | "build" | "collection" | "enrichment";

export interface NavItem {
  id: ViewId;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "match", label: "Match-overzicht" },
  { id: "buy", label: "Koop-wachtrij" },
  { id: "build", label: "Playlist builder" },
  { id: "collection", label: "Collectie" },
  { id: "enrichment", label: "Genre-verrijking" },
];

// A trailing counter is rendered only where a real number exists (the
// prototype's "128", "4 fases" and "8.412 tracks" are demo data). `accent`
// picks the prototype's green counter, used for the buy queue.
export interface NavCounter {
  value: string;
  accent?: boolean;
}
