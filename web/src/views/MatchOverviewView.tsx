import { useEffect, useRef, useState } from "react";

import { ApplyAction } from "../features/spotify-sync/ApplyAction";
import { MatchFilters } from "../features/spotify-sync/MatchFilters";
import { MatchReport, MissingTracks } from "../features/spotify-sync/MatchReport";
import { groupOf, isGroupVisible, sortTracks } from "../features/spotify-sync/matchFilters";
import type { MatchFilter, MatchSort } from "../features/spotify-sync/matchFilters";
import { PlaylistUrlForm } from "../features/spotify-sync/PlaylistUrlForm";
import { SpotifyConnection } from "../features/spotify-sync/SpotifyConnection";
import type {
  SpotifyConnectionStatus,
  SyncSession,
  SyncSessionDetail,
} from "../features/spotify-sync/types";
import { ReviewView } from "../features/review/ReviewView";

interface MatchOverviewViewProps {
  session: SyncSessionDetail | null;
  onSessionCreated: (session: SyncSession) => void;
  onSessionChanged: () => void;
  onSpotifyStatus: (status: SpotifyConnectionStatus | null) => void;
  onGoToBuyQueue: () => void;
  // Incremented by the top bar's "Sync" pill: switch here and focus the URL
  // field. 0 means "not requested", so the field is not stolen on load.
  focusUrlToken: number;
}

const PRIMARY_PILL =
  "inline-flex h-34 items-center justify-center rounded-full-2 bg-pure-white px-16 text-body font-bold whitespace-nowrap text-void-black hover:bg-chalk focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

interface GroupHeadingProps {
  dot: string;
  title: string;
  meta?: string;
}

// The prototype's group heading: 8px dot, 14px/700 title, muted count.
function GroupHeading({ dot, title, meta }: GroupHeadingProps) {
  return (
    <div className="flex items-center gap-10">
      <span aria-hidden="true" className={`h-8 w-8 flex-none rounded-full ${dot}`} />
      <h2 className="text-body-lg font-bold text-pure-white">{title}</h2>
      {meta && <p className="text-body-sm text-mist">{meta}</p>}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  note: string;
  accent?: boolean;
}

function StatCard({ label, value, note, accent }: StatCardProps) {
  return (
    <div className="flex flex-col gap-6 rounded-md bg-graphite p-16">
      <span className="text-caption tracking-stat text-mist">{label}</span>
      <span
        className={`text-heading leading-heading font-bold ${accent ? "text-spotify-green" : "text-pure-white"}`}
      >
        {value}
      </span>
      <span className="text-caption text-mist">{note}</span>
    </div>
  );
}

// The prototype's Match-overzicht view (HANDOFF.md, "1. Match-overzicht"),
// carrying US1 (connect + paste a playlist), US2 (review the doubtful
// matches) and US3 (write the result back to Rekordbox).
//
// The filter chips and the sort control live here rather than inside one of
// the groups: the design's groups are rendered by two different feature
// components (the missing table in spotify-sync/MatchReport, the review cards
// in review/ReviewView), and only an owner above both can make a chip
// actually filter and the sort actually reorder all of them.
//
// Deliberately not built, because the data does not exist:
// - the "GEEN ANALYSE / BPM/key ontbreekt" stat card -- no analysis-status
//   field exists on a sync track (features/spotify-sync/types.ts);
// - the missing-track table's LABEL, BPM and KEY columns and its store/price
//   cell (reasons in MatchReport.tsx, at the table itself);
// - the year on the review card's Spotify side -- a SyncTrack carries no
//   release date, and Spotify's audio-features/album detail is not fetched;
// - the "Exporteer XML" pill -- writing to Rekordbox goes through the guarded
//   database writer, and XML export is out of scope (ADR 0008).
export function MatchOverviewView({
  session,
  onSessionCreated,
  onSessionChanged,
  onSpotifyStatus,
  onGoToBuyQueue,
  focusUrlToken,
}: MatchOverviewViewProps) {
  const urlInputRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<MatchFilter>("all");
  // The design's own default caption is "Sorteer op zekerheid".
  const [sort, setSort] = useState<MatchSort>("score");

  useEffect(() => {
    if (focusUrlToken > 0) urlInputRef.current?.focus();
  }, [focusUrlToken]);

  const totals = session?.totals;
  const trackCount = session?.tracks.length ?? 0;
  const matchedPct = totals && trackCount > 0 ? Math.round((totals.matched / trackCount) * 100) : 0;

  const tracks = session?.tracks ?? [];
  const missingTracks = sortTracks(
    tracks.filter((track) => groupOf(track.status) === "missing"),
    sort,
  );
  const collectionTracks = sortTracks(
    tracks.filter((track) => groupOf(track.status) === "collection"),
    sort,
  );
  const reviewCount = tracks.filter((track) => groupOf(track.status) === "review").length;

  return (
    <div className="flex flex-col gap-28">
      <div className="flex flex-wrap items-end gap-20">
        <div
          aria-hidden="true"
          className="h-132 w-132 flex-none rounded-md bg-[linear-gradient(135deg,var(--color-magenta-glow),var(--color-promo-gradient))]"
        />
        <div className="flex flex-col gap-10 pb-4">
          <p className="text-caption font-bold tracking-eyebrow text-mist">
            SPOTIFY PLAYLIST · MATCH-RAPPORT
          </p>
          <h1 className="text-heading leading-heading font-bold text-pure-white">
            {session ? session.name : "Match-overzicht"}
          </h1>
          <p className="text-body text-mist">
            {session && totals
              ? `${trackCount} tracks · ${totals.matched} in collectie · ${totals.review} twijfelgevallen · ${totals.missing} ontbreken`
              : "Plak een Spotify-afspeellijst-URL om een match-rapport te maken."}
          </p>
        </div>
        <div className="flex-1" />
        <div className="flex flex-wrap justify-end gap-8">
          <button type="button" onClick={onGoToBuyQueue} className={PRIMARY_PILL}>
            Ontbrekende naar wachtrij
          </button>
        </div>
      </div>

      {totals && (
        // Four of the five real totals. `rejected` has no card of its own --
        // it is a review outcome, not a match outcome -- and appears in the
        // full report below, which lists all five.
        <div className="grid grid-cols-2 gap-12 lg:grid-cols-4">
          <StatCard
            label="IN COLLECTIE"
            value={totals.matched}
            note={`${matchedPct}% van de afspeellijst`}
            accent
          />
          <StatCard label="TWIJFEL" value={totals.review} note="jij kiest de juiste match" />
          <StatCard label="ONTBREEKT" value={totals.missing} note="niet in de collectie gevonden" />
          <StatCard
            label="NIET TE MATCHEN"
            value={totals.unmatchable}
            note="geen bruikbare metadata"
          />
        </div>
      )}

      <section className="flex flex-col gap-16">
        <GroupHeading dot="bg-spotify-green" title="Spotify-verbinding" />
        <SpotifyConnection onStatusChange={onSpotifyStatus} />
      </section>

      <section className="flex flex-col gap-16">
        <GroupHeading dot="bg-bone" title="Afspeellijst matchen" />
        <PlaylistUrlForm inputRef={urlInputRef} onSessionCreated={onSessionCreated} />
      </section>

      {session && (
        <MatchFilters
          filter={filter}
          onFilterChange={setFilter}
          sort={sort}
          onSortChange={setSort}
        />
      )}

      {/* The design's groups, in its own order: what is missing first, then
          what needs a decision, then what is already in the collection. Each
          heading is a coloured dot (decoration) plus text that carries the
          meaning, and the chips above decide which of them render. */}
      {session && isGroupVisible(filter, "missing") && (
        <section className="flex flex-col gap-16">
          <GroupHeading
            dot="bg-signal-red"
            title="Ontbreekt in Rekordbox"
            meta={`${missingTracks.length} tracks`}
          />
          <MissingTracks tracks={missingTracks} onGoToBuyQueue={onGoToBuyQueue} />
        </section>
      )}

      {session && isGroupVisible(filter, "review") && (
        <section className="flex flex-col gap-16">
          <GroupHeading
            dot="bg-bone"
            title="Twijfelgevallen — jouw beslissing"
            meta={`${reviewCount} tracks`}
          />
          <ReviewView session={session} sort={sort} onResolved={onSessionChanged} />
        </section>
      )}

      {session && isGroupVisible(filter, "collection") && (
        <section className="flex flex-col gap-16">
          <GroupHeading
            dot="bg-spotify-green"
            title="In collectie"
            meta={`${collectionTracks.length} van ${trackCount} tracks`}
          />
          <MatchReport totals={session.totals} tracks={collectionTracks} />
        </section>
      )}

      {session && (
        <section className="flex flex-col gap-16">
          <GroupHeading dot="bg-bone" title="Naar Rekordbox schrijven" />
          <ApplyAction
            sessionId={session.id}
            defaultPlaylistName={session.name}
            onApplied={onSessionChanged}
          />
        </section>
      )}
    </div>
  );
}
