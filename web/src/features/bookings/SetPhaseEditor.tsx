import { useId, useState } from "react";

import type { TreeNodeDto } from "../../components/Tree";

// The phase columns are the structure's playlist nodes and their `set_phase`
// (ADR 0008: a free-text label, explicitly not logic), so a structure with no
// `set_phase` anywhere has no phases -- and nothing in the tree editor can set
// one. This is where the DJ gives a playlist its phase, with the spec's four
// examples offered as a datalist rather than as a closed list.

const PHASE_SUGGESTIONS = ["vooravond", "mid", "prime", "sluit"];

export interface SetPhaseEditorProps {
  nodes: TreeNodeDto[];
  onSave: (nodeId: number, setPhase: string | null) => void;
}

interface SetPhaseRowProps {
  node: TreeNodeDto;
  onSave: SetPhaseEditorProps["onSave"];
}

function SetPhaseRow({ node, onSave }: SetPhaseRowProps) {
  const [draft, setDraft] = useState(node.set_phase ?? "");
  const inputId = useId();
  const listId = useId();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSave(node.id, draft.trim() === "" ? null : draft.trim());
      }}
      className="flex flex-wrap items-center gap-8"
    >
      <label htmlFor={inputId} className="text-body-lg font-semibold">
        {`Setfase voor ${node.name}`}
      </label>
      <input
        id={inputId}
        type="text"
        list={listId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="min-h-24 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      />
      <datalist id={listId}>
        {PHASE_SUGGESTIONS.map((phase) => (
          <option key={phase} value={phase} />
        ))}
      </datalist>
      <button
        type="submit"
        className="min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      >
        {`Setfase opslaan: ${node.name}`}
      </button>
    </form>
  );
}

export function SetPhaseEditor({ nodes, onSave }: SetPhaseEditorProps) {
  const playlists = nodes
    .filter((node) => node.kind === "playlist")
    .slice()
    .sort((a, b) => a.position - b.position);

  return (
    <div className="flex flex-col gap-8">
      <h2 className="text-body-lg font-bold text-pure-white">Setfases</h2>
      {playlists.length === 0 ? (
        <p className="text-body-lg text-mist">
          Maak eerst een playlist in de boom hieronder; daarna kun je die een setfase geven.
        </p>
      ) : (
        playlists.map((node) => <SetPhaseRow key={node.id} node={node} onSave={onSave} />)
      )}
    </div>
  );
}
