import { useEffect, useRef, useState } from "react";

import { phaseBpmRangeText, phaseDurationText } from "./phaseModel";
import type { Phase, PhaseTrack } from "./phaseModel";

// The design's four-column grid of phase cards (HANDOFF.md "3. Playlist
// builder"), one card per playlist node that carries a `set_phase`. Below
// 1280px (Tailwind's xl) it drops to two columns, as the handoff's responsive
// note asks.
//
// Moving a track between phases: the design says drag. Drag alone fails WCAG
// 2.2, so the keyboard path is the real one and pointer dragging is the
// addition on top of it -- every row carries "naar vorige/volgende fase"
// buttons with an accessible name, focus stays on the moved row in its new
// column, and the move is announced in a live region.

const MOVE_BUTTON_CLASSES =
  "min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-8 text-caption font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

export interface PhaseBoardProps {
  phases: Phase[];
  // Resolves to a Dutch error message, or null when the move succeeded.
  onMove: (rbContentId: string, fromNodeId: number, toNodeId: number) => Promise<string | null>;
}

function focusKeyFor(nodeId: number, rbContentId: string): string {
  return `${nodeId}:${rbContentId}`;
}

interface DraggedTrack {
  rbContentId: string;
  fromNodeId: number;
  title: string;
}

interface TrackRowProps {
  track: PhaseTrack;
  index: number;
  phase: Phase;
  previousPhase: Phase | null;
  nextPhase: Phase | null;
  registerButton: (key: string, element: HTMLButtonElement | null) => void;
  onMoveTo: (track: PhaseTrack, phase: Phase, target: Phase) => void;
  onDragStart: (dragged: DraggedTrack) => void;
}

function TrackRow({
  track,
  index,
  phase,
  previousPhase,
  nextPhase,
  registerButton,
  onMoveTo,
  onDragStart,
}: TrackRowProps) {
  // The row's first move button is the anchor focus returns to after a move,
  // registered under the row key so the destination column can find it again.
  const anchorKey = focusKeyFor(phase.node_id, track.rb_content_id);
  function anchorRef(element: HTMLButtonElement | null) {
    registerButton(anchorKey, element);
  }
  const anchorIsPreviousButton = previousPhase !== null;

  return (
    <li
      draggable
      onDragStart={(event) => {
        onDragStart({
          rbContentId: track.rb_content_id,
          fromNodeId: phase.node_id,
          title: track.title,
        });
        if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
      }}
      className="flex cursor-grab items-center gap-10 border-b border-smoke px-14 py-9 hover:bg-smoke"
    >
      <span className="w-14 shrink-0 text-caption text-mist">{index + 1}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-body-sm font-semibold text-pure-white">
          {track.title}
        </span>
        <span className="block truncate text-caption text-mist">{track.artist}</span>
      </span>
      <span className="shrink-0 text-right">
        <span className="block text-caption text-pure-white">
          {track.bpm === null
            ? track.facts_resolved
              ? "geen BPM"
              : "BPM ?"
            : `${Math.round(track.bpm)} BPM`}
        </span>
        <span className="block text-micro text-spotify-green">
          {track.musical_key === null
            ? track.facts_resolved
              ? "geen toonaard"
              : "toonaard ?"
            : track.musical_key}
        </span>
      </span>
      <span className="flex shrink-0 gap-4">
        {previousPhase && (
          <button
            type="button"
            ref={anchorRef}
            onClick={() => onMoveTo(track, phase, previousPhase)}
            className={MOVE_BUTTON_CLASSES}
          >
            <span aria-hidden="true">←</span>
            <span className="sr-only">{`Verplaats ${track.title} naar fase ${previousPhase.label}`}</span>
          </button>
        )}
        {nextPhase && (
          <button
            type="button"
            ref={anchorIsPreviousButton ? undefined : anchorRef}
            onClick={() => onMoveTo(track, phase, nextPhase)}
            className={MOVE_BUTTON_CLASSES}
          >
            <span aria-hidden="true">→</span>
            <span className="sr-only">{`Verplaats ${track.title} naar fase ${nextPhase.label}`}</span>
          </button>
        )}
      </span>
    </li>
  );
}

export function PhaseBoard({ phases, onMove }: PhaseBoardProps) {
  const [announcement, setAnnouncement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const dragged = useRef<DraggedTrack | null>(null);
  const pendingFocus = useRef<string | null>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  function registerButton(key: string, element: HTMLButtonElement | null) {
    if (element === null) buttons.current.delete(key);
    else buttons.current.set(key, element);
  }

  // WCAG 2.2: after the move the row lives in another column, so focus has to
  // follow it there rather than being dropped back to the document.
  useEffect(() => {
    const key = pendingFocus.current;
    if (key === null) return;
    const target = buttons.current.get(key);
    if (target) {
      target.focus();
      pendingFocus.current = null;
    }
  }, [phases]);

  async function move(track: PhaseTrack, from: Phase, to: Phase) {
    pendingFocus.current = focusKeyFor(to.node_id, track.rb_content_id);
    const failure = await onMove(track.rb_content_id, from.node_id, to.node_id);
    if (failure !== null) {
      pendingFocus.current = null;
      setError(failure);
      setAnnouncement("");
      return;
    }
    setError(null);
    setAnnouncement(`${track.title} verplaatst van fase ${from.label} naar fase ${to.label}.`);
  }

  function handleDrop(target: Phase) {
    const source = dragged.current;
    dragged.current = null;
    if (source === null || source.fromNodeId === target.node_id) return;
    const from = phases.find((phase) => phase.node_id === source.fromNodeId);
    const track = from?.tracks.find((item) => item.rb_content_id === source.rbContentId);
    if (!from || !track) return;
    void move(track, from, target);
  }

  if (phases.length === 0) {
    return (
      <div className="flex flex-col gap-8 rounded-md bg-graphite p-16">
        <h2 className="text-body-lg font-bold text-pure-white">Fases</h2>
        <p className="text-body-sm text-mist">
          Deze structuur heeft nog geen fases. Geef een playlist hieronder een setfase (bijvoorbeeld
          vooravond, mid, prime of sluit); die playlist wordt dan een fasekolom.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-12">
      <h2 className="text-body-lg font-bold text-pure-white">Fases</h2>
      <p role="status" className="text-body-sm text-mist">
        {announcement}
      </p>
      {error && (
        <p role="alert" className="text-body-sm font-semibold text-pure-white">
          {error}
        </p>
      )}
      {/* Four columns above the width the handoff names for the phase grid, two
          below it. The width is the `--breakpoint-phases` token rather than
          Tailwind's `xl`, which only happens to be the same number today. */}
      <ul className="grid grid-cols-1 items-start gap-12 sm:grid-cols-2 phases:grid-cols-4">
        {phases.map((phase, phaseIndex) => (
          <li
            key={phase.node_id}
            className="rounded-md bg-graphite"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleDrop(phase);
            }}
          >
            <div className="flex flex-col gap-4 border-b border-smoke px-14 pt-14 pb-12">
              <div className="flex items-baseline justify-between gap-8">
                <h3 className="min-w-0 truncate text-body-lg font-bold text-pure-white">
                  {phase.label}
                </h3>
                <span className="shrink-0 text-caption text-mist">{phaseDurationText(phase)}</span>
              </div>
              <p className="text-caption text-mist">
                {`${phase.node_name} · ${phaseBpmRangeText(phase)} · ${phase.tracks.length} ${phase.tracks.length === 1 ? "nummer" : "nummers"}`}
                {phase.applied ? " · toegepast in Rekordbox" : ""}
              </p>
            </div>
            {phase.tracks.length === 0 ? (
              <p className="px-14 py-9 text-caption text-mist">Nog geen nummers in deze fase.</p>
            ) : (
              <ul>
                {phase.tracks.map((track, index) => (
                  <TrackRow
                    key={track.rb_content_id}
                    track={track}
                    index={index}
                    phase={phase}
                    previousPhase={phaseIndex > 0 ? phases[phaseIndex - 1] : null}
                    nextPhase={phaseIndex < phases.length - 1 ? phases[phaseIndex + 1] : null}
                    registerButton={registerButton}
                    onMoveTo={(item, from, to) => void move(item, from, to)}
                    onDragStart={(source) => {
                      dragged.current = source;
                    }}
                  />
                ))}
              </ul>
            )}
            <p className="px-14 py-10 text-caption text-mist">
              + track hierheen slepen, of met de pijlknoppen verplaatsen
            </p>
          </li>
        ))}
      </ul>
      {/* Honest about what the API can tell us: there is no endpoint that
          returns a node's stored track order, so the rows are in the order the
          suggestions endpoint reports them (play count), not the set order. */}
      <p className="text-caption text-mist">
        De volgorde binnen een fase is de afspeelfrequentie uit de collectie: de API levert de
        opgeslagen volgorde van een fase-playlist nog niet.
      </p>
    </div>
  );
}
