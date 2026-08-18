import { useEffect, useId, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { Tree } from "../../components/Tree";
import type { TreeNodeDto } from "../../components/Tree";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";
import type { ApplyResultDto, ProfileDto, StructureDto, SuggestionDto } from "./types";

// Same code-keyed-switch convention as MissingQueue.tsx/Tree.tsx's error
// mappers: Dutch text for known codes, the raw backend message as a last
// resort -- a guard/backup refusal's own message already names the fix
// (contracts/api.md), so passing it through here is correct, not a gap.
function applyErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "structure_not_found":
      return "Deze structuur bestaat niet meer.";
    default:
      return error.message || "Toepassen is mislukt. Probeer het opnieuw.";
  }
}

interface StructureFormProps {
  onCreate: (name: string) => void;
}

function StructureForm({ onCreate }: StructureFormProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Vul een naam in.");
      return;
    }
    setError(null);
    onCreate(trimmed);
    setName("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8">
      <label htmlFor={inputId} className="text-body-lg font-semibold">
        Naam nieuwe structuur
      </label>
      <div className="flex flex-wrap gap-8">
        <input
          id={inputId}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          className="min-h-24 flex-1 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
        <button
          type="submit"
          className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          Structuur aanmaken
        </button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
    </form>
  );
}

interface ProfileFormProps {
  onCreate: (
    name: string,
    bpmMin: number | null,
    bpmMax: number | null,
    genreTags: string[],
  ) => void;
}

function ProfileForm({ onCreate }: ProfileFormProps) {
  const [name, setName] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [genreTags, setGenreTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const bpmMinId = useId();
  const bpmMaxId = useId();
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Vul een naam in.");
      return;
    }
    setError(null);
    const tags = genreTags
      .split(",")
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0);
    onCreate(trimmed, bpmMin ? Number(bpmMin) : null, bpmMax ? Number(bpmMax) : null, tags);
    setName("");
    setBpmMin("");
    setBpmMax("");
    setGenreTags("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8">
      <label htmlFor={inputId} className="text-body-lg font-semibold">
        Naam nieuw profiel
      </label>
      <input
        id={inputId}
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        aria-invalid={error !== null}
        aria-describedby={error ? errorId : undefined}
        className="min-h-24 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      />
      <div className="flex flex-wrap gap-8">
        <label htmlFor={bpmMinId} className="text-body-lg font-semibold">
          BPM min
        </label>
        <input
          id={bpmMinId}
          type="number"
          value={bpmMin}
          onChange={(event) => setBpmMin(event.target.value)}
          className="min-h-24 flex-1 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
        <label htmlFor={bpmMaxId} className="text-body-lg font-semibold">
          BPM max
        </label>
        <input
          id={bpmMaxId}
          type="number"
          value={bpmMax}
          onChange={(event) => setBpmMax(event.target.value)}
          className="min-h-24 flex-1 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
      </div>
      <input
        type="text"
        value={genreTags}
        onChange={(event) => setGenreTags(event.target.value)}
        placeholder="genre tags, komma-gescheiden"
        className="min-h-24 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white placeholder-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      />
      <button
        type="submit"
        className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      >
        Profiel aanmaken
      </button>
      {error && (
        <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
    </form>
  );
}

// T088 (FR-031..FR-035, FR-018, WCAG): profile editor, suggestion list
// (accept/dismiss, already-in-playlist flag), apply action and result
// state, naming-error inputs. Composes Tree.tsx (T087) for the folder/
// playlist tree itself.
export function BookingWorkspace() {
  const [structures, setStructures] = useState<StructureDto[] | null>(null);
  const [profiles, setProfiles] = useState<ProfileDto[] | null>(null);
  const [selectedStructureId, setSelectedStructureId] = useState<number | null>(null);
  const [nodes, setNodes] = useState<TreeNodeDto[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionDto[]>([]);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  // Tree.tsx's move/nest/lift actions each fire two independent onMove
  // calls (a position swap, or a re-parent) in the same click. Each call
  // triggers its own PUT + refreshNodes; without sequencing, the two
  // requests can land and refresh out of order, so whichever one's
  // refreshNodes happens to resolve last can silently drop the other's
  // change from the rendered tree (review finding). A single promise
  // chain forces every mutation's full PUT-then-refetch cycle to finish
  // before the next one starts.
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());

  function enqueueMutation(task: () => Promise<void>) {
    mutationQueueRef.current = mutationQueueRef.current.then(task, task);
  }

  async function refreshStructures() {
    try {
      const { data } = await apiClient.GET("/api/structures");
      setStructures(asApiResponse<StructureDto[]>(data) ?? []);
    } catch {
      setStructures((current) => current ?? []);
    }
  }

  async function refreshProfiles() {
    try {
      const { data } = await apiClient.GET("/api/profiles");
      setProfiles(asApiResponse<ProfileDto[]>(data) ?? []);
    } catch {
      setProfiles((current) => current ?? []);
    }
  }

  useEffect(() => {
    void refreshStructures();
    void refreshProfiles();
  }, []);

  async function refreshNodes(structureId: number) {
    const { data } = await apiClient.GET("/api/structures/{structure_id}/nodes", {
      params: { path: { structure_id: structureId } },
    });
    setNodes(asApiResponse<TreeNodeDto[]>(data) ?? []);
  }

  async function refreshSuggestions(structureId: number, nodeId: number) {
    const { data } = await apiClient.GET(
      "/api/structures/{structure_id}/nodes/{node_id}/suggestions",
      { params: { path: { structure_id: structureId, node_id: nodeId } } },
    );
    setSuggestions(asApiResponse<SuggestionDto[]>(data) ?? []);
  }

  async function handleSelectStructure(id: number) {
    setSelectedStructureId(id);
    setSelectedNodeId(null);
    setSuggestions([]);
    setApplyMessage(null);
    await refreshNodes(id);
  }

  async function handleSelectNode(nodeId: number) {
    setSelectedNodeId(nodeId);
    if (selectedStructureId !== null) {
      await refreshSuggestions(selectedStructureId, nodeId);
    }
  }

  async function handleCreateStructure(name: string) {
    await apiClient.POST("/api/structures", { body: { name, booking_profile_id: null } });
    await refreshStructures();
  }

  async function handleCreateProfile(
    name: string,
    bpmMin: number | null,
    bpmMax: number | null,
    genreTags: string[],
  ) {
    await apiClient.POST("/api/profiles", {
      body: { name, bpm_min: bpmMin, bpm_max: bpmMax, genre_tags: genreTags },
    });
    await refreshProfiles();
  }

  async function handleCreateNode(parentId: number | null, kind: "folder" | "playlist") {
    if (selectedStructureId === null) return;
    const siblingCount = nodes.filter((n) => n.parent_id === parentId).length;
    await apiClient.POST("/api/structures/{structure_id}/nodes", {
      params: { path: { structure_id: selectedStructureId } },
      body: {
        kind,
        name: kind === "folder" ? "Nieuwe map" : "Nieuwe playlist",
        parent_id: parentId,
        position: siblingCount,
        set_phase: null,
      },
    });
    await refreshNodes(selectedStructureId);
  }

  async function handleRenameNode(nodeId: number, name: string): Promise<ApiError | null> {
    if (selectedStructureId === null) return null;
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;
    const { error } = await apiClient.PUT("/api/structures/{structure_id}/nodes/{node_id}", {
      params: { path: { structure_id: selectedStructureId, node_id: nodeId } },
      body: { name, parent_id: node.parent_id, position: node.position, set_phase: node.set_phase },
    });
    if (error) return asApiResponse<ApiError>(error);
    await refreshNodes(selectedStructureId);
    return null;
  }

  async function handleMoveNode(nodeId: number, parentId: number | null, position: number) {
    if (selectedStructureId === null) return;
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;
    await apiClient.PUT("/api/structures/{structure_id}/nodes/{node_id}", {
      params: { path: { structure_id: selectedStructureId, node_id: nodeId } },
      body: { name: node.name, parent_id: parentId, position, set_phase: node.set_phase },
    });
    await refreshNodes(selectedStructureId);
  }

  async function handleDeleteNode(nodeId: number) {
    if (selectedStructureId === null) return;
    await apiClient.DELETE("/api/structures/{structure_id}/nodes/{node_id}", {
      params: { path: { structure_id: selectedStructureId, node_id: nodeId } },
    });
    await refreshNodes(selectedStructureId);
  }

  async function handleAccept(track: SuggestionDto) {
    if (selectedStructureId === null || selectedNodeId === null) return;
    await apiClient.POST("/api/structures/{structure_id}/nodes/{node_id}/tracks", {
      params: { path: { structure_id: selectedStructureId, node_id: selectedNodeId } },
      body: { rb_content_id: track.rb_content_id, origin: "suggestion" },
    });
    await refreshSuggestions(selectedStructureId, selectedNodeId);
  }

  async function handleDismiss(track: SuggestionDto) {
    if (selectedStructureId === null || selectedNodeId === null) return;
    await apiClient.POST("/api/structures/{structure_id}/nodes/{node_id}/dismissals", {
      params: { path: { structure_id: selectedStructureId, node_id: selectedNodeId } },
      body: { rb_content_id: track.rb_content_id },
    });
    await refreshSuggestions(selectedStructureId, selectedNodeId);
  }

  async function handleApply() {
    if (selectedStructureId === null) return;
    setApplyMessage(null);
    const { data, error } = await apiClient.POST("/api/structures/{structure_id}/apply", {
      params: { path: { structure_id: selectedStructureId } },
    });
    if (error) {
      setApplyMessage(applyErrorMessageFor(asApiResponse<ApiError>(error)));
      return;
    }
    const result = asApiResponse<ApplyResultDto>(data);
    const tracksAdded = result.nodes.reduce((total, node) => total + node.tracks_added, 0);
    setApplyMessage(`Toegepast: ${tracksAdded} nummer(s) toegevoegd.`);
    await refreshNodes(selectedStructureId);
  }

  if (structures === null || profiles === null) {
    return (
      <p role="status" className="text-body-lg text-mist">
        Structuren laden…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-16">
      <p className="text-heading font-bold">Booking Structures</p>

      <div className="flex flex-wrap gap-8" role="group" aria-label="Structuren">
        {structures.map((structure) => (
          <button
            key={structure.id}
            type="button"
            onClick={() => void handleSelectStructure(structure.id)}
            aria-pressed={selectedStructureId === structure.id}
            className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            {structure.name}
          </button>
        ))}
      </div>
      <StructureForm onCreate={(name) => void handleCreateStructure(name)} />

      <ProfileForm
        onCreate={(name, bpmMin, bpmMax, genreTags) =>
          void handleCreateProfile(name, bpmMin, bpmMax, genreTags)
        }
      />

      {selectedStructureId !== null && (
        <>
          <Tree
            nodes={nodes}
            onCreate={(parentId, kind) => void handleCreateNode(parentId, kind)}
            onRename={handleRenameNode}
            onMove={(id, parentId, position) =>
              enqueueMutation(() => handleMoveNode(id, parentId, position))
            }
            onDelete={(id) => void handleDeleteNode(id)}
            onSelect={(id) => void handleSelectNode(id)}
            selectedId={selectedNodeId}
          />

          {selectedNodeId !== null && (
            <div className="flex flex-col gap-8">
              <p className="text-body-lg font-semibold text-pure-white">Suggesties</p>
              {suggestions.length === 0 ? (
                <p className="text-body-lg text-mist">Geen suggesties.</p>
              ) : (
                <ul className="flex flex-col gap-8">
                  {suggestions.map((track) => (
                    <li
                      key={track.rb_content_id}
                      className="flex flex-wrap items-center gap-8 rounded-md bg-graphite p-16 text-pure-white"
                    >
                      <span className="text-body-lg font-semibold">
                        {track.artist} – {track.title}
                      </span>
                      <span className="text-body-lg text-mist">
                        {`Al in de playlist: ${track.already_in_playlist ? "ja" : "nee"}`}
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleAccept(track)}
                        className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
                      >
                        {`Accepteren: ${track.artist} – ${track.title}`}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDismiss(track)}
                        className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
                      >
                        {`Afwijzen: ${track.artist} – ${track.title}`}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex flex-col gap-8">
            <button
              type="button"
              onClick={() => void handleApply()}
              className="min-h-24 rounded-full-2 bg-spotify-green px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
            >
              Toepassen
            </button>
            {applyMessage && (
              <p role="status" className="text-body-lg font-semibold text-pure-white">
                {applyMessage}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
