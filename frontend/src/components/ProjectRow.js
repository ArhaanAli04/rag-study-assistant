// One project in the Projects panel: rename, instructions, archive, its files and chats, delete.
// Each action keeps its own busy and error state, so a failure shows next to the control that failed.
import { useCallback, useEffect, useState } from "react";
import { Archive, ChevronDown, ChevronRight, Loader2, Pencil, ScrollText, Trash2 } from "lucide-react";
import {
  deleteProject,
  getProject,
  plural,
  PROJECT_INSTRUCTIONS_MAX,
  PROJECT_NAME_MAX,
  projectCounts,
  projectDeletedNotice,
  updateProject,
} from "../services/projectsApi";

const buttonClass = "inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs hover:bg-white/10 disabled:opacity-50";

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

function RenameForm({ project, busy, onCancel, onSave }) {
  const [name, setName] = useState(project.name);
  const trimmed = name.trim();
  return (
    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (trimmed) onSave(trimmed); }}>
      <label htmlFor={`rename-${project.id}`} className="sr-only">New name for {project.name}</label>
      <input id={`rename-${project.id}`} value={name} maxLength={PROJECT_NAME_MAX} disabled={busy}
        onChange={(e) => setName(e.target.value)}
        className="flex-1 px-3 py-1.5 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground" />
      <button type="submit" className={buttonClass} disabled={busy || !trimmed || trimmed === project.name}>
        {busy ? "Saving…" : "Save name"}
      </button>
      <button type="button" className={buttonClass} disabled={busy} onClick={onCancel}>Cancel</button>
    </form>
  );
}

function InstructionsEditor({ project, onSaved }) {
  const [text, setText] = useState(project.instructions || "");
  const [state, setState] = useState("idle"); // idle | saving | saved | error
  const [error, setError] = useState(null);
  const id = `instructions-${project.id}`;

  const save = async () => {
    setState("saving");
    setError(null);
    try {
      await updateProject(project.id, { instructions: text });
      setState("saved");
      await onSaved();
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  };

  return (
    <div className="mt-2">
      <label htmlFor={id} className="block text-xs text-muted-foreground mb-1">
        Instructions for every chat in {project.name} (focus, tone, format). They can't override how answers cite sources.
      </label>
      <textarea id={id} value={text} rows={4} maxLength={PROJECT_INSTRUCTIONS_MAX} disabled={state === "saving"}
        onChange={(e) => { setText(e.target.value); setState("idle"); }}
        placeholder="e.g. Answer in bullet points and use the notation from the lectures."
        className="w-full px-3 py-2 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground" />
      <div className="flex items-center justify-between mt-1">
        <span className="text-xs text-muted-foreground">{text.length} / {PROJECT_INSTRUCTIONS_MAX}</span>
        <div className="flex items-center gap-2">
          {state === "saved" && <span role="status" className="text-xs text-emerald-400">Saved</span>}
          {state === "error" && <span role="alert" className="text-xs text-destructive">{error}</span>}
          <button type="button" className={buttonClass} disabled={state === "saving"} onClick={save}>
            {state === "saving" ? "Saving…" : "Save instructions"}
          </button>
        </div>
      </div>
    </div>
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

function DeleteDialog({ project, busy, onCancel, onConfirm }) {
  const [documents, setDocuments] = useState(null);
  const files = project.document_count ?? 0;
  return (
    <div role="dialog" aria-label={`Delete ${project.name}`} className="mt-2 p-3 rounded-lg border border-destructive/30 bg-destructive/5">
      <p className="text-sm text-foreground mb-2">
        Delete {project.name}? {plural(project.chat_count ?? 0, "chat")} will move to No project. What should
        happen to its {plural(files, "file")}?
      </p>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="radio" name={`delete-${project.id}`} value="unassign" disabled={busy}
          checked={documents === "unassign"} onChange={() => setDocuments("unassign")} />
        Keep them: move them to No project
      </label>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="radio" name={`delete-${project.id}`} value="delete" disabled={busy}
          checked={documents === "delete"} onChange={() => setDocuments("delete")} />
        Delete them too (they won't be cited again)
      </label>
      <div className="flex gap-2 mt-3">
        <button type="button" className={`${buttonClass} text-destructive`} disabled={busy || documents === null}
          onClick={() => onConfirm(documents)}>
          {busy ? "Deleting…" : "Delete project"}
        </button>
        <button type="button" className={buttonClass} disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
