// One project in the Projects panel: rename, instructions, archive, its files and chats, delete.
// Each action keeps its own busy and error state, so a failure shows next to the control that failed.
import { useCallback, useEffect, useState } from "react";
import { Archive, ChevronDown, ChevronRight, Loader2, Pencil, ScrollText, Trash2 } from "lucide-react";
import {
  deleteProject,
  getProject,
  projectCounts,
  projectDeletedNotice,
  updateProject,
} from "../services/projectsApi";
import { buttonClass, DeleteDialog, InstructionsEditor, RenameForm } from "./ProjectEditors";

export default function ProjectRow({ project, onChanged }) {
  const [open, setOpen] = useState(null); // null | "rename" | "instructions" | "details" | "delete"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggle = (panel) => {
    setError(null);
    setOpen(open === panel ? null : panel);
  };

  const run = async (action) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const archive = () => run(async () => {
    await updateProject(project.id, { archived: !project.archived });
    await onChanged(project.archived ? `Unarchived ${project.name}.` : `Archived ${project.name}: it takes no new files or chats.`);
  });

  return (
    <li className="py-3" aria-label={`Project ${project.name}`}>
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => toggle("details")} className="text-muted-foreground"
                aria-expanded={open === "details"} aria-label={`Show files and chats of ${project.name}`}>
          {open === "details" ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium text-foreground">{project.name}</span>
          {project.archived && (
            <span className="ml-2 text-xs px-2 py-0.5 rounded-md border border-amber-500/30 text-amber-400">Archived</span>
          )}
          <p className="text-xs text-muted-foreground">{projectCounts(project)}</p>
        </div>
        <button type="button" className={buttonClass} disabled={busy} onClick={() => toggle("rename")}>
          <Pencil className="w-3 h-3" aria-hidden="true" /> Rename
        </button>
        <button type="button" className={buttonClass} disabled={busy} onClick={() => toggle("instructions")}>
          <ScrollText className="w-3 h-3" aria-hidden="true" /> Instructions
        </button>
        <button type="button" className={buttonClass} disabled={busy} onClick={archive}>
          <Archive className="w-3 h-3" aria-hidden="true" /> {project.archived ? "Unarchive" : "Archive"}
        </button>
        <button type="button" className={`${buttonClass} text-destructive`} disabled={busy} onClick={() => toggle("delete")}>
          <Trash2 className="w-3 h-3" aria-hidden="true" /> Delete
        </button>
      </div>

      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}

      {open === "rename" && (
        <RenameForm project={project} busy={busy} onCancel={() => setOpen(null)}
          onSave={(name) => run(async () => {
            await updateProject(project.id, { name });
            setOpen(null);
            await onChanged(`Renamed to ${name}.`);
          })} />
      )}
      {open === "instructions" && (
        <InstructionsEditor project={project} onSaved={() => onChanged(`Saved the instructions of ${project.name}.`)} />
      )}
      {open === "details" && <ProjectDetails projectId={project.id} />}
      {open === "delete" && (
        <DeleteDialog project={project} busy={busy} onCancel={() => setOpen(null)}
          onConfirm={(documents) => run(async () => {
            const result = await deleteProject(project.id, documents);
            await onChanged(projectDeletedNotice(project.name, result));
          })} />
      )}
    </li>
  );
}

function ProjectDetails({ projectId }) {
  const [state, setState] = useState({ loading: true, error: null, detail: null });

  // Loaded when the row is expanded (this component mounts then), and again on "Try again".
  const load = useCallback(async () => {
    setState({ loading: true, error: null, detail: null });
    try {
      setState({ loading: false, error: null, detail: await getProject(projectId) });
    } catch (err) {
      setState({ loading: false, error: err.message, detail: null });
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.loading) {
    return (
      <div role="status" className="mt-2 ml-7 flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" /> Loading files and chats…
      </div>
    );
  }
  if (state.error) {
    return (
      <p role="alert" className="mt-2 ml-7 text-xs text-destructive">
        Couldn't load this project: {state.error}{" "}
        <button type="button" className="underline" onClick={load}>Try again</button>
      </p>
    );
  }
  const { documents, chats } = state.detail;
  if (documents.length === 0 && chats.length === 0) {
    return <p className="mt-2 ml-7 text-xs text-muted-foreground">No files or chats in this project yet.</p>;
  }
  return (
    <div className="mt-2 ml-7 grid grid-cols-2 gap-4 text-xs">
      <div>
        <p className="font-medium text-foreground mb-1">Files</p>
        {documents.length === 0 ? <p className="text-muted-foreground">No files yet.</p> : (
          <ul>{documents.map((d) => (
            <li key={d.id} className="text-muted-foreground truncate">
              {d.filename}{d.chunks === 0 ? " (not searchable yet)" : ""}
            </li>
          ))}</ul>
        )}
      </div>
      <div>
        <p className="font-medium text-foreground mb-1">Chats</p>
        {chats.length === 0 ? <p className="text-muted-foreground">No chats yet.</p> : (
          <ul>{chats.map((c) => <li key={c.id} className="text-muted-foreground truncate">{c.title || `Chat ${c.id}`}</li>)}</ul>
        )}
      </div>
    </div>
  );
}
