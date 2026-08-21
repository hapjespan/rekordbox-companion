import { bpmBars, setBpmRangeText, setDurationText } from "./phaseModel";
import type { Phase } from "./phaseModel";

// The design's "Energiecurve" card, in its shape but not under its name: it
// plots BPM, not energy. Spotify's audio-features endpoint answers 403 for
// this application, so no per-track energy value exists anywhere, and a chart
// drawn from an invented one would be a lie. Hence "BPM-verloop", and a track
// without a BPM gets no bar at all.
//
// Accessibility: a row of coloured bars is not readable, so the bars are
// decorative (aria-hidden) and the same numbers are available as a real table
// underneath. The peak bars are the tallest bars by construction (peak = the
// highest BPM in the set), so their green fill is redundant with their height
// and no state is carried by colour alone.

export interface BpmProgressionCardProps {
  phases: Phase[];
}

export function BpmProgressionCard({ phases }: BpmProgressionCardProps) {
  const bars = bpmBars(phases);
  const rulerPhases = phases.filter((phase) => phase.tracks.length > 0);

  return (
    <section aria-labelledby="bpm-progression-title" className="rounded-md bg-graphite p-20">
      <div className="flex flex-col gap-14">
        <div className="flex flex-wrap items-baseline gap-12">
          <h2 id="bpm-progression-title" className="text-body-lg font-bold text-pure-white">
            BPM-verloop
          </h2>
          <span className="text-body-sm text-mist">{setBpmRangeText(phases)}</span>
          <span className="text-body-sm text-mist">{setDurationText(phases)}</span>
          <span className="ml-auto text-caption text-mist">
            Elke balk is één track · BPM uit Rekordbox, geen energiewaarde
          </span>
        </div>

        {bars.length === 0 ? (
          <p className="text-body-sm text-mist">
            Nog geen nummers in de fases, dus nog geen BPM-verloop.
          </p>
        ) : (
          <>
            <div aria-hidden="true" className="flex h-120 items-end gap-3">
              {/* Keyed by position, not by rb_content_id: nothing stops the
                  same track from sitting in two phase playlists, and two bars
                  sharing a key is a React identity bug. */}
              {bars.map((bar, index) => (
                <div
                  key={`${bar.phase_label}-${bar.rb_content_id}-${index}`}
                  className="flex h-full flex-1 items-end"
                >
                  {bar.height_percent !== null && (
                    <div
                      className={`w-full rounded-sm ${bar.is_peak ? "bg-spotify-green" : "bg-steel"}`}
                      style={{ height: `${bar.height_percent}%` }}
                    />
                  )}
                </div>
              ))}
            </div>

            {rulerPhases.length > 0 && (
              <div
                aria-hidden="true"
                className="grid gap-3"
                style={{
                  gridTemplateColumns: rulerPhases
                    .map((phase) => `${phase.tracks.length}fr`)
                    .join(" "),
                }}
              >
                {rulerPhases.map((phase) => (
                  <span key={phase.node_id} className="truncate text-caption text-mist">
                    {phase.label}
                  </span>
                ))}
              </div>
            )}

            <details>
              <summary className="cursor-pointer text-body-sm text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green">
                Tekstalternatief: BPM per track
              </summary>
              <table className="mt-12 w-full text-left">
                <caption className="sr-only">
                  BPM per track, in dezelfde volgorde als de balken. Een track zonder BPM heeft geen
                  balk.
                </caption>
                <thead>
                  <tr className="text-caption tracking-table text-mist">
                    <th scope="col" className="py-4 pr-12 font-normal">
                      #
                    </th>
                    <th scope="col" className="py-4 pr-12 font-normal">
                      Fase
                    </th>
                    <th scope="col" className="py-4 pr-12 font-normal">
                      Track
                    </th>
                    <th scope="col" className="py-4 pr-12 font-normal">
                      BPM
                    </th>
                    <th scope="col" className="py-4 font-normal">
                      Piek
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {bars.map((bar, index) => (
                    <tr
                      key={`${bar.phase_label}-${bar.rb_content_id}-${index}`}
                      className="text-body-sm text-pure-white"
                    >
                      <td className="py-4 pr-12">{index + 1}</td>
                      <td className="py-4 pr-12">{bar.phase_label}</td>
                      <td className="py-4 pr-12">{`${bar.artist} – ${bar.title}`}</td>
                      <td className="py-4 pr-12">
                        {bar.bpm === null ? "onbekend" : String(Math.round(bar.bpm))}
                      </td>
                      <td className="py-4">{bar.is_peak ? "ja" : "nee"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
