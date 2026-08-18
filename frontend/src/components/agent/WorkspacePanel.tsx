import { useEffect, useState } from "react";
import { Folder, FileText, RotateCcw, RefreshCw } from "lucide-react";
import { workspaceApi } from "@/lib/api-endpoints";
import { useAgentCatalogStore } from "@/stores/agent-catalog-store";
import { toast } from "@/stores/ui-store";
import { ApiError } from "@/lib/api-client";
import type { FileEdit } from "@/lib/types";
import { DiffView } from "@/components/agent/DiffView";
import { Button } from "@/components\ui\Button";
import { Skeleton } from "@/components\ui\Skeleton";

export function WorkspacePanel() {
  const selectedId = useAgentCatalogStore((s) => s.selectedId);
  const [files, setFiles] = useState<string[]>([]);
  const [edits, setEdits] = useState<FileEdit[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);

  const load = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const [f, e] = await Promise.all([
        workspaceApi.files(selectedId),
        workspaceApi.edits(selectedId, { limit: 20 }),
      ]);
      setFiles(f.files);
      setEdits(e.data);
    } catch (err) {
      if ((err as ApiError)?.statusCode !== 404) {
        toast.error(err instanceof ApiError ? err.detail : "Could not load workspace.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setFiles([]);
    setEdits([]);
    setSelectedFile(null);
    setFileContent(null);
    if (selectedId) void load();
  }, [selectedId]);

  const openFile = async (path: string) => {
    if (!selectedId) return;
    setSelectedFile(path);
    try {
      const data = await workspaceApi.file(selectedId, path);
      setFileContent(data.content);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Could not read file.");
    }
  };

  const undo = async (editId: string) => {
    if (!selectedId) return;
    try {
      await workspaceApi.undo(selectedId, editId);
      toast.success("Undone.");
      void load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Undo failed.");
    }
  };

  if (!selectedId) {
    return <p className="p-4 text-center text-sm text-text-muted">Select an agent to view its workspace.</p>;
  }

  return (
    <div className="flex flex-col gap-4 p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Workspace</span>
        <Button variant="ghost" size="sm" leftIcon={<RefreshCw size={13} />} onClick={load} isLoading={loading}>
          Refresh
        </Button>
      </div>

      {/* File browser */}
      <div>
        <p className="mb-1 flex items-center gap-1 text-[0.7rem] font-medium uppercase tracking-wide text-text-muted">
          <Folder size={12} /> Files
        </p>
        {loading && files.length === 0 ? (
          <Skeleton className="h-10 w-full" />
        ) : files.length === 0 ? (
          <p className="text-xs text-text-muted">No files yet.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {files.map((f) => (
              <button
                key={f}
                onClick={() => openFile(f)}
                className={`flex items-center gap-1.5 rounded px-2 py-1 text-left font-mono text-xs hover:bg-bg-tertiary ${selectedFile === f ? "bg-bg-tertiary text-accent-primary" : "text-text-secondary"}`}
              >
                <FileText size={12} /> {f}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedFile && fileContent !== null && (
        <div>
          <p className="mb-1 text-[0.7rem] font-medium uppercase tracking-wide text-text-muted">{selectedFile}</p>
          <pre className="max-h-64 overflow-auto rounded bg-bg-primary p-2 font-mono text-xs text-text-secondary">{fileContent}</pre>
        </div>
      )}

      {/* History timeline */}
      <div>
        <p className="mb-1 text-[0.7rem] font-medium uppercase tracking-wide text-text-muted">History</p>
        {edits.length === 0 ? (
          <p className="text-xs text-text-muted">No edits yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {edits.map((e) => (
              <div key={e.id} className="rounded border border-border bg-bg-secondary/40 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-xs text-text-primary">{e.path}</span>
                  <Button variant="ghost" size="sm" leftIcon={<RotateCcw size={12} />} onClick={() => undo(e.id)}>
                    Undo
                  </Button>
                </div>
                <p className="text-[0.65rem] text-text-muted">{new Date(e.created_at).toLocaleString()} · {e.store}</p>
                <div className="mt-1">
                  <DiffView patch={e.patch} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
