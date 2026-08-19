import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import { asApiResponse } from "../features/spotify-sync/types";
import { Tree } from "./Tree";
import type { TreeNode } from "./Tree";

// GET /api/playlists (contracts/api.md): the Rekordbox playlist tree, flat,
// each node carrying its parent. `parent_id` is null for a top-level node.
export interface PlaylistNodeDto {
  rb_playlist_id: string;
  name: string;
  parent_id: string | null;
  is_folder: boolean;
  position: number;
}

export interface SelectedRekordboxPlaylist {
  id: string;
  name: string;
}

interface RekordboxLibraryProps {
  // The Collection view filters to the chosen playlist; it needs the name to
  // say which playlist it is showing.
  onSelect: (playlist: SelectedRekordboxPlaylist) => void;
  selectedId?: string | null;
}

function errorMessageFor(apiError: unknown): string {
  const code = (apiError as { code?: string } | undefined)?.code;
  if (code === "rekordbox_not_found") {
    return "Rekordbox is niet gevonden. Start Rekordbox en herlaad de pagina.";
  }
  return "Kon je Rekordbox-bibliotheek niet laden. Probeer het opnieuw.";
}

function toTreeNodes(nodes: PlaylistNodeDto[]): TreeNode<string>[] {
  return nodes.map((node) => ({
    id: node.rb_playlist_id,
    parent_id: node.parent_id,
    kind: node.is_folder ? "folder" : "playlist",
    name: node.name,
    position: node.position,
  }));
}

// The sidebar's Rekordbox section: the library as the hierarchical, foldable
// tree Rekordbox itself shows. The hierarchy is reconstructed here from
// `parent_id`, and rendered by the app's one Tree component (components/
// Tree.tsx, "compact" variant) rather than a second tree implementation.
export function RekordboxLibrary({ onSelect, selectedId }: RekordboxLibraryProps) {
  const [nodes, setNodes] = useState<PlaylistNodeDto[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data, error: apiError } = await apiClient.GET("/api/playlists");
        if (cancelled) return;
        if (apiError) {
          setError(errorMessageFor(apiError));
          setNodes(null);
          return;
        }
        setError(null);
        setNodes(asApiResponse<PlaylistNodeDto[] | undefined>(data) ?? []);
      } catch {
        if (!cancelled) {
          setError(errorMessageFor(undefined));
          setNodes(null);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const treeNodes = useMemo(() => (nodes ? toTreeNodes(nodes) : []), [nodes]);
  const nameById = useMemo(
    () => new Map((nodes ?? []).map((node) => [node.rb_playlist_id, node.name])),
    [nodes],
  );

  if (error) {
    return (
      <p role="alert" className="text-caption leading-body text-pure-white">
        {error}
      </p>
    );
  }

  if (nodes === null) {
    return <p className="text-caption leading-body text-mist">Bibliotheek laden…</p>;
  }

  if (nodes.length === 0) {
    return (
      <p className="text-caption leading-body text-mist">Geen playlists in Rekordbox gevonden.</p>
    );
  }

  return (
    <Tree
      variant="compact"
      label="Rekordbox-bibliotheek"
      nodes={treeNodes}
      selectedId={selectedId ?? null}
      onSelect={(id) => onSelect({ id, name: nameById.get(id) ?? id })}
    />
  );
}
