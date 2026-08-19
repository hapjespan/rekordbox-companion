import { useEffect, useId, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { Tree, nextPositionAmong } from "../../components/Tree";
import type { TreeNodeDto } from "../../components/Tree";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";
import { BpmProgressionCard } from "./BpmProgressionCard";
import { ChecksBar } from "./ChecksBar";
import { PhaseBoard } from "./PhaseBoard";
import { SetPhaseEditor } from "./SetPhaseEditor";
import { buildPhases, computeChecks, isPhaseNode } from "./phaseModel";
import type { PhaseTrack } from "./phaseModel";
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

// One page of Suggestions per request: the endpoint's `limit` is not
// optional in practice -- an unfiltered call returns the whole Collection
// (tens of thousands of rows at the project's sizing envelope), which is a
// multi-MB response and a list item with two buttons per track in the DOM.
const SUGGESTION_PAGE_SIZE = 50;

// What a phase playlist holds comes from the node's own tracks endpoint
// (`GET .../nodes/{nid}/tracks`): real membership, in the stored
// `structure_track.position` order, with every row already carrying artist,
// title, BPM, key and duration. Deliberately NOT the Suggestions endpoint's
// `already_in_playlist` flag, which is filtered by the profile and ranked by
// play count and therefore shows a wrongly ordered subset.
//
// The endpoint's own maximum page size, so a phase of up to 200 tracks costs
// exactly one request; a longer one is paged out in full rather than silently
// truncated.
const NODE_TRACK_PAGE_SIZE = 200;

interface NodeTrackPageDto {
  total: number;
  items: PhaseTrack[];
}

// A missing track that is still `open` has not been bought yet (FR-021).
interface MissingTrackRefDto {
  artist: string;
  title: string;
  status: string;
}

const INPUT_CLASSES =
  "min-h-24 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

const PRIMARY_BUTTON_CLASSES =
  "min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

const SECONDARY_BUTTON_CLASSES =
  "min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

function parseGenreTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

interface StructureFormProps {
  profiles: ProfileDto[];
  onCreate: (name: string, bookingProfileId: number | null) => void;
}

function StructureForm({ profiles, onCreate }: StructureFormProps) {
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const profileSelectId = useId();
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Vul een naam in.");
      return;
    }
    setError(null);
    onCreate(trimmed, profileId === "" ? null : Number(profileId));
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
          className={`flex-1 ${INPUT_CLASSES}`}
        />
        <label htmlFor={profileSelectId} className="text-body-lg font-semibold">
          Profiel
        </label>
        <select
          id={profileSelectId}
          value={profileId}
          onChange={(event) => setProfileId(event.target.value)}
          className={INPUT_CLASSES}
        >
          <option value="">Geen profiel</option>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.name}
            </option>
          ))}
        </select>
        <button type="submit" className={PRIMARY_BUTTON_CLASSES}>
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

interface ProfileFieldsFormProps {
  legend: string;
  nameLabel: string;
  submitLabel: string;
  initialName?: string;
  initialBpmMin?: number | null;
  initialBpmMax?: number | null;
  initialGenreTags?: string[];
  resetAfterSubmit?: boolean;
  onSubmit: (
    name: string,
    bpmMin: number | null,
    bpmMax: number | null,
    genreTags: string[],
  ) => void;
}

// One form body for creating a profile and for editing one: FR-031 makes the
// same three things editable in both directions (name, genre tags, BPM
// range), so they live in a single component instead of two that drift. The
// caller keys an edit instance by profile id, so switching profiles remounts
// it with that profile's values as the drafts.
function ProfileFieldsForm({
  legend,
  nameLabel,
  submitLabel,
  initialName = "",
  initialBpmMin = null,
  initialBpmMax = null,
  initialGenreTags = [],
  resetAfterSubmit = false,
  onSubmit,
}: ProfileFieldsFormProps) {
  const [name, setName] = useState(initialName);
  const [bpmMin, setBpmMin] = useState(initialBpmMin === null ? "" : String(initialBpmMin));
  const [bpmMax, setBpmMax] = useState(initialBpmMax === null ? "" : String(initialBpmMax));
  const [genreTags, setGenreTags] = useState(initialGenreTags.join(", "));
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const bpmMinId = useId();
  const bpmMaxId = useId();
  const genreTagsId = useId();
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Vul een naam in.");
      return;
    }
    setError(null);
    onSubmit(
      trimmed,
      bpmMin ? Number(bpmMin) : null,
      bpmMax ? Number(bpmMax) : null,
      parseGenreTags(genreTags),
    );
    if (resetAfterSubmit) {
      setName("");
      setBpmMin("");
      setBpmMax("");
      setGenreTags("");
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <fieldset className="flex flex-col gap-8 border-0 p-0">
        <legend className="text-body-lg font-semibold text-pure-white">{legend}</legend>
        <label htmlFor={inputId} className="text-body-lg font-semibold">
          {nameLabel}
        </label>
        <input
          id={inputId}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          className={INPUT_CLASSES}
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
            className={`flex-1 ${INPUT_CLASSES}`}
          />
          <label htmlFor={bpmMaxId} className="text-body-lg font-semibold">
            BPM max
          </label>
          <input
            id={bpmMaxId}
            type="number"
            value={bpmMax}
            onChange={(event) => setBpmMax(event.target.value)}
            className={`flex-1 ${INPUT_CLASSES}`}
          />
        </div>
        <label htmlFor={genreTagsId} className="text-body-lg font-semibold">
          Genre tags, komma-gescheiden
        </label>
        <input
          id={genreTagsId}
          type="text"
          value={genreTags}
          onChange={(event) => setGenreTags(event.target.value)}
          className={INPUT_CLASSES}
        />
        <button type="submit" className={PRIMARY_BUTTON_CLASSES}>
          {submitLabel}
        </button>
        {error && (
          <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
            {error}
          </p>
        )}
      </fieldset>
    </form>
  );
}

interface ProfileEditorProps {
  profiles: ProfileDto[];
  onSave: (
    profileId: number,
    name: string,
    bpmMin: number | null,
    bpmMax: number | null,
    genreTags: string[],
  ) => void;
}

// US7 scenario 1 / FR-031: the seeded profiles (horeca, bruiloft, prive,
// thema) start with no genre tags and no BPM range by design (ADR 0008), so
// without this editor a profile can never be given the filters Suggestions
// are supposed to be driven by.
function ProfileEditor({ profiles, onSave }: ProfileEditorProps) {
  const [chosenId, setChosenId] = useState<number | null>(null);
  const selectId = useId();

  if (profiles.length === 0) {
    return <p className="text-body-lg text-mist">Nog geen profielen.</p>;
  }

  const selected = profiles.find((profile) => profile.id === chosenId) ?? profiles[0];

  return (
    <div className="flex flex-col gap-8">
      <label htmlFor={selectId} className="text-body-lg font-semibold">
        Profiel bewerken
      </label>
      <select
        id={selectId}
        value={selected.id}
        onChange={(event) => setChosenId(Number(event.target.value))}
        className={INPUT_CLASSES}
      >
        {profiles.map((profile) => (
          <option key={profile.id} value={profile.id}>
            {profile.name}
          </option>
        ))}
      </select>
      <ProfileFieldsForm
        key={selected.id}
        legend={`Profiel ${selected.name}`}
        nameLabel="Naam profiel"
        submitLabel="Profiel opslaan"
        initialName={selected.name}
        initialBpmMin={selected.bpm_min}
        initialBpmMax={selected.bpm_max}
        initialGenreTags={selected.genre_tags}
        onSubmit={(name, bpmMin, bpmMax, genreTags) =>
          onSave(selected.id, name, bpmMin, bpmMax, genreTags)
        }
      />
    </div>
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
  const [suggestionLimit, setSuggestionLimit] = useState(SUGGESTION_PAGE_SIZE);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [phaseTracks, setPhaseTracks] = useState<Record<number, PhaseTrack[]>>({});
  const [openBuyQueue, setOpenBuyQueue] = useState<{ artist: string; title: string }[]>([]);
  const structureProfileSelectId = useId();
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

  // The checks bar's "still in the buy queue" item (FR-021's open items),
  // matched on artist and title: a MissingTrack is a Spotify track that is not
  // in the collection, so it carries no rb_content_id to join on.
  async function refreshOpenBuyQueue() {
    try {
      const { data } = await apiClient.GET("/api/missing", {
        params: { query: { status: "open" } },
      });
      const rows = asApiResponse<MissingTrackRefDto[]>(data) ?? [];
      setOpenBuyQueue(
        rows
          .filter((row) => row.status === "open")
          .map((row) => ({ artist: row.artist, title: row.title })),
      );
    } catch {
      setOpenBuyQueue([]);
    }
  }

  useEffect(() => {
    void refreshStructures();
    void refreshProfiles();
    void refreshOpenBuyQueue();
  }, []);

  // The node's stored tracks, in their stored order. One request per phase
  // playlist for anything up to a full page; only a phase holding more than
  // NODE_TRACK_PAGE_SIZE tracks costs a second one, and then it is because the
  // endpoint said there are more, never a guess.
  async function fetchNodeTracks(structureId: number, nodeId: number): Promise<PhaseTrack[]> {
    const rows: PhaseTrack[] = [];
    let total = 0;
    do {
      let body: NodeTrackPageDto | undefined;
      try {
        const { data, error } = await apiClient.GET(
          "/api/structures/{structure_id}/nodes/{node_id}/tracks",
          {
            params: {
              path: { structure_id: structureId, node_id: nodeId },
              query: { limit: NODE_TRACK_PAGE_SIZE, offset: rows.length },
            },
          },
        );
        if (error) break;
        body = asApiResponse<NodeTrackPageDto | undefined>(data);
      } catch {
        // A phase whose tracks could not be read stays empty rather than
        // taking the whole builder down; the request is retried on the next
        // refresh.
        break;
      }
      if (!body) break;
      total = body.total;
      const items = body.items ?? [];
      if (items.length === 0) break;
      rows.push(...items);
    } while (rows.length < total);
    return rows;
  }

  async function refreshPhaseData(structureId: number, currentNodes: TreeNodeDto[]) {
    const tracksByNode: Record<number, PhaseTrack[]> = {};
    for (const node of currentNodes.filter(isPhaseNode)) {
      tracksByNode[node.id] = await fetchNodeTracks(structureId, node.id);
    }
    setPhaseTracks(tracksByNode);
  }

  async function refreshNodes(structureId: number) {
    const { data } = await apiClient.GET("/api/structures/{structure_id}/nodes", {
      params: { path: { structure_id: structureId } },
    });
    const list = asApiResponse<TreeNodeDto[]>(data) ?? [];
    setNodes(list);
    await refreshPhaseData(structureId, list);
  }

  // `limit` is always sent: the endpoint treats its absence as "the whole
  // Collection", which at 20k+ tracks is a multi-MB response and tens of
  // thousands of DOM nodes for one click (phase 7 review finding). "Toon
  // meer" raises the limit a page at a time.
  async function refreshSuggestions(structureId: number, nodeId: number, limit: number) {
    const { data } = await apiClient.GET(
      "/api/structures/{structure_id}/nodes/{node_id}/suggestions",
      {
        params: { path: { structure_id: structureId, node_id: nodeId }, query: { limit } },
      },
    );
    setSuggestions(asApiResponse<SuggestionDto[]>(data) ?? []);
  }

  async function handleSelectStructure(id: number) {
    setSelectedStructureId(id);
    setSelectedNodeId(null);
    setSuggestions([]);
    setSuggestionLimit(SUGGESTION_PAGE_SIZE);
    setApplyMessage(null);
    await refreshNodes(id);
  }

  async function handleSelectNode(nodeId: number) {
    setSelectedNodeId(nodeId);
    setSuggestionLimit(SUGGESTION_PAGE_SIZE);
    if (selectedStructureId !== null) {
      await refreshSuggestions(selectedStructureId, nodeId, SUGGESTION_PAGE_SIZE);
    }
  }

  async function handleShowMoreSuggestions() {
    if (selectedStructureId === null || selectedNodeId === null) return;
    const nextLimit = suggestionLimit + SUGGESTION_PAGE_SIZE;
    setSuggestionLimit(nextLimit);
    await refreshSuggestions(selectedStructureId, selectedNodeId, nextLimit);
  }

  async function handleCreateStructure(name: string, bookingProfileId: number | null) {
    await apiClient.POST("/api/structures", {
      body: { name, booking_profile_id: bookingProfileId },
    });
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

  // FR-031 "editable": without this the seeded profiles keep the empty genre
  // tags and BPM range they are seeded with, and Suggestions can only ever
  // run unfiltered (US7 scenario 1).
  async function handleSaveProfile(
    profileId: number,
    name: string,
    bpmMin: number | null,
    bpmMax: number | null,
    genreTags: string[],
  ) {
    await apiClient.PUT("/api/profiles/{profile_id}", {
      params: { path: { profile_id: profileId } },
      body: { name, bpm_min: bpmMin, bpm_max: bpmMax, genre_tags: genreTags },
    });
    await refreshProfiles();
    // The profile drives this structure's Suggestions, so a saved filter
    // must show up in the open list instead of waiting for a re-select.
    if (selectedStructureId !== null && selectedNodeId !== null) {
      await refreshSuggestions(selectedStructureId, selectedNodeId, suggestionLimit);
    }
  }

  // FR-033/US7 scenario 3: Suggestions are filtered by the structure's
  // Booking Profile, so the structure needs a way to point at one.
  async function handleLinkProfile(bookingProfileId: number | null) {
    const structure = structures?.find((s) => s.id === selectedStructureId);
    if (selectedStructureId === null || !structure) return;
    await apiClient.PUT("/api/structures/{structure_id}", {
      params: { path: { structure_id: selectedStructureId } },
      body: { name: structure.name, booking_profile_id: bookingProfileId },
    });
    await refreshStructures();
    if (selectedNodeId !== null) {
      await refreshSuggestions(selectedStructureId, selectedNodeId, suggestionLimit);
    }
  }

  async function handleCreateNode(parentId: number | null, kind: "folder" | "playlist") {
    if (selectedStructureId === null) return;
    await apiClient.POST("/api/structures/{structure_id}/nodes", {
      params: { path: { structure_id: selectedStructureId } },
      body: {
        kind,
        name: kind === "folder" ? "Nieuwe map" : "Nieuwe playlist",
        parent_id: parentId,
        // max()+1, not the sibling count: a count reuses a position once a
        // non-trailing sibling has been deleted (the collision class already
        // fixed in the backend's add_track and in Tree.nextPositionAmong,
        // which this shares).
        position: nextPositionAmong(nodes, parentId),
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

  // FR-032: `set_phase` is what makes a playlist node a phase column, and the
  // tree editor has no field for it. Sending the node's own name back
  // unchanged keeps the rename-lock on an applied node satisfied.
  async function handleSetPhase(nodeId: number, setPhase: string | null) {
    if (selectedStructureId === null) return;
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;
    await apiClient.PUT("/api/structures/{structure_id}/nodes/{node_id}", {
      params: { path: { structure_id: selectedStructureId, node_id: nodeId } },
      body: {
        name: node.name,
        parent_id: node.parent_id,
        position: node.position,
        set_phase: setPhase,
      },
    });
    await refreshNodes(selectedStructureId);
  }

  // Moving a track between two phase playlists is an add to the target plus a
  // remove from the source; the backend refuses the remove once a node is
  // applied to Rekordbox, so that case is answered here before anything is
  // written rather than leaving the track in both playlists.
  async function handleMovePhaseTrack(
    rbContentId: string,
    fromNodeId: number,
    toNodeId: number,
  ): Promise<string | null> {
    if (selectedStructureId === null) return "Geen structuur geselecteerd.";
    const from = nodes.find((n) => n.id === fromNodeId);
    if (from?.rb_ref) {
      return "Deze fase is al toegepast in Rekordbox; verplaats het nummer daar.";
    }
    try {
      const { error: addError } = await apiClient.POST(
        "/api/structures/{structure_id}/nodes/{node_id}/tracks",
        {
          params: { path: { structure_id: selectedStructureId, node_id: toNodeId } },
          body: { rb_content_id: rbContentId, origin: "manual" },
        },
      );
      if (addError) return applyErrorMessageFor(asApiResponse<ApiError>(addError));
      const { error: removeError } = await apiClient.DELETE(
        "/api/structures/{structure_id}/nodes/{node_id}/tracks/{rb_content_id}",
        {
          params: {
            path: {
              structure_id: selectedStructureId,
              node_id: fromNodeId,
              rb_content_id: rbContentId,
            },
          },
        },
      );
      if (removeError) return applyErrorMessageFor(asApiResponse<ApiError>(removeError));
    } catch {
      // FR-026's silent-failure ban: a failed request must say so, not leave
      // the row looking as if it moved (or as if nothing was clicked).
      return "Verplaatsen is mislukt. Probeer het opnieuw.";
    }
    await refreshNodes(selectedStructureId);
    return null;
  }

  async function handleAccept(track: SuggestionDto) {
    if (selectedStructureId === null || selectedNodeId === null) return;
    await apiClient.POST("/api/structures/{structure_id}/nodes/{node_id}/tracks", {
      params: { path: { structure_id: selectedStructureId, node_id: selectedNodeId } },
      body: { rb_content_id: track.rb_content_id, origin: "suggestion" },
    });
    await refreshSuggestions(selectedStructureId, selectedNodeId, suggestionLimit);
    // The accepted track now sits in a phase playlist, so the phase columns,
    // the BPM bars and the checks all have to take it into account.
    await refreshPhaseData(selectedStructureId, nodes);
  }

  async function handleDismiss(track: SuggestionDto) {
    if (selectedStructureId === null || selectedNodeId === null) return;
    await apiClient.POST("/api/structures/{structure_id}/nodes/{node_id}/dismissals", {
      params: { path: { structure_id: selectedStructureId, node_id: selectedNodeId } },
      body: { rb_content_id: track.rb_content_id },
    });
    await refreshSuggestions(selectedStructureId, selectedNodeId, suggestionLimit);
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

  const phases = buildPhases(nodes, phaseTracks);
  const checks = computeChecks(phases, openBuyQueue);

  return (
    <div className="flex flex-col gap-16">
      {/* The panel title is the Playlist builder view's own <h1> now. */}
      <div className="flex flex-wrap gap-8" role="group" aria-label="Structuren">
        {structures.map((structure) => (
          <button
            key={structure.id}
            type="button"
            onClick={() => void handleSelectStructure(structure.id)}
            aria-pressed={selectedStructureId === structure.id}
            className={SECONDARY_BUTTON_CLASSES}
          >
            {structure.name}
          </button>
        ))}
      </div>
      <StructureForm
        profiles={profiles}
        onCreate={(name, bookingProfileId) => void handleCreateStructure(name, bookingProfileId)}
      />

      <ProfileFieldsForm
        legend="Nieuw profiel"
        nameLabel="Naam nieuw profiel"
        submitLabel="Profiel aanmaken"
        resetAfterSubmit
        onSubmit={(name, bpmMin, bpmMax, genreTags) =>
          void handleCreateProfile(name, bpmMin, bpmMax, genreTags)
        }
      />

      <ProfileEditor
        profiles={profiles}
        onSave={(profileId, name, bpmMin, bpmMax, genreTags) =>
          void handleSaveProfile(profileId, name, bpmMin, bpmMax, genreTags)
        }
      />

      {selectedStructureId !== null && (
        <>
          {/* The design's order for this view: the curve card, the phase
              columns, then the checks bar (HANDOFF.md "3. Playlist builder").
              The structure/profile/tree editing this workspace already had
              follows underneath. */}
          <BpmProgressionCard phases={phases} />

          <PhaseBoard phases={phases} onMove={handleMovePhaseTrack} />

          <ChecksBar checks={checks} />

          <SetPhaseEditor
            nodes={nodes}
            onSave={(nodeId, setPhase) => void handleSetPhase(nodeId, setPhase)}
          />

          <div className="flex flex-col gap-8">
            <label htmlFor={structureProfileSelectId} className="text-body-lg font-semibold">
              Profiel voor deze structuur
            </label>
            <select
              id={structureProfileSelectId}
              value={structures.find((s) => s.id === selectedStructureId)?.booking_profile_id ?? ""}
              onChange={(event) =>
                void handleLinkProfile(
                  event.target.value === "" ? null : Number(event.target.value),
                )
              }
              className={INPUT_CLASSES}
            >
              <option value="">Geen profiel</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </div>

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
              {/* B9: a real heading, not a styled paragraph. */}
              <h2 className="text-body-lg font-bold text-pure-white">Suggesties</h2>
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
                        className={SECONDARY_BUTTON_CLASSES}
                      >
                        {`Accepteren: ${track.artist} – ${track.title}`}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDismiss(track)}
                        className={SECONDARY_BUTTON_CLASSES}
                      >
                        {`Afwijzen: ${track.artist} – ${track.title}`}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {/* A full page came back, so there is probably another one. */}
              {suggestions.length >= suggestionLimit && (
                <button
                  type="button"
                  onClick={() => void handleShowMoreSuggestions()}
                  className={SECONDARY_BUTTON_CLASSES}
                >
                  Toon meer suggesties
                </button>
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
