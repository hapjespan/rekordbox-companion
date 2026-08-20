// Small display formatters shared by the Match-overzicht groups (the
// delivered design writes durations as "6:48" and row indexes as "01").
// Kept out of the components so the missing table, the review card and any
// later group format the same values identically.

export function formatDuration(durationMs: number | null | undefined): string | null {
  if (durationMs === null || durationMs === undefined || durationMs < 0) return null;
  const totalSeconds = Math.round(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

// The prototype numbers its rows "01".."05" (two digits), and keeps counting
// past 99 without padding.
export function formatPosition(position: number): string {
  return String(position).padStart(2, "0");
}
