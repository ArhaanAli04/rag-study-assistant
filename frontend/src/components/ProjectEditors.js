// The editing controls of a project (Day 18, shared since Day 19 by the Projects list, a project's
// page and the Documents page panel): rename, description, instructions and the delete dialog.
// Each reports through its own callbacks, so the page that hosts it decides what to refresh.
import { useState } from "react";
import {
  plural,
  PROJECT_DESCRIPTION_MAX,
  PROJECT_INSTRUCTIONS_MAX,
  PROJECT_NAME_MAX,
  updateProject,
} from "../services/projectsApi";

export const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60";
export const buttonClass =
  `inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-foreground hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${focusRing}`;
export const inputClass =
  `w-full px-3 py-2 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-muted-foreground ${focusRing}`;

export function RenameForm({ project, busy, onCancel, onSave }) {
  const [name, setName] = useState(project.name);
  const trimmed = name.trim();
  return (
    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (trimmed) onSave(trimmed); }}>
      <label htmlFor={`rename-${project.id}`} className="sr-only">New name for {project.name}</label>
      <input id={`rename-${project.id}`} value={name} maxLength={PROJECT_NAME_MAX} disabled={busy}
        onChange={(e) => setName(e.target.value)}
        className={`flex-1 min-w-0 px-3 py-1.5 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground ${focusRing}`} />
      <button type="submit" className={buttonClass} disabled={busy || !trimmed || trimmed === project.name}>
        {busy ? "Saving…" : "Save name"}
      </button>
      <button type="button" className={buttonClass} disabled={busy} onClick={onCancel}>Cancel</button>
    </form>
  );
}

// A text field of the project saved with its own button: idle | saving | saved | error, plus an
// "Unsaved changes" marker while the box differs from what the server holds (BrowserRouter can't
// block navigation, so the marker is the warning).
function useSavedText(project, field) {
  const [saved, setSaved] = useState(project[field] || "");
  const [text, setText] = useState(saved);
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);

  const save = async (onSaved) => {
    setState("saving");
    setError(null);
    try {
      await updateProject(project.id, { [field]: text });
      setSaved(text.trim()); // the server stores it trimmed
      setState("saved");
      await onSaved();
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  };

  const edit = (value) => {
    setText(value);
    setState("idle");
  };

  return { text, edit, state, error, save, unsaved: text.trim() !== saved };
}

function SaveRow({ count, max, field, onSave, buttonLabel }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 mt-1">
      <span className="text-xs text-muted-foreground">{count} / {max}</span>
      <div className="flex items-center gap-2">
        {field.unsaved && field.state !== "saving" && (
          <span className="text-xs text-amber-400">Unsaved changes</span>
        )}
        {field.state === "saved" && <span role="status" className="text-xs text-emerald-400">Saved</span>}
        {field.state === "error" && <span role="alert" className="text-xs text-destructive">{field.error}</span>}
        <button type="button" className={buttonClass} disabled={field.state === "saving"} onClick={onSave}>
          {field.state === "saving" ? "Saving…" : buttonLabel}
        </button>
      </div>
    </div>
  );
}

export function InstructionsEditor({ project, onSaved, rows = 4 }) {
  const field = useSavedText(project, "instructions");
  const id = `instructions-${project.id}`;
  return (
    <div className="mt-2">
      <label htmlFor={id} className="block text-xs text-muted-foreground mb-1">
        Instructions for every chat in {project.name} (focus, tone, format). They can't override how answers cite sources.
      </label>
      <textarea id={id} value={field.text} rows={rows} maxLength={PROJECT_INSTRUCTIONS_MAX}
        disabled={field.state === "saving"} onChange={(e) => field.edit(e.target.value)}
        placeholder="e.g. Answer in bullet points and use the notation from the lectures."
        className={inputClass} />
      <SaveRow count={field.text.length} max={PROJECT_INSTRUCTIONS_MAX} field={field} buttonLabel="Save instructions"
        onSave={() => field.save(onSaved)} />
    </div>
  );
}

export function DescriptionEditor({ project, onSaved }) {
  const field = useSavedText(project, "description");
  const id = `description-${project.id}`;
  return (
    <div className="mt-2">
      <label htmlFor={id} className="block text-xs text-muted-foreground mb-1">
        Description of {project.name} (what the course covers; only you see it)
      </label>
      <textarea id={id} value={field.text} rows={2} maxLength={PROJECT_DESCRIPTION_MAX}
        disabled={field.state === "saving"} onChange={(e) => field.edit(e.target.value)}
        placeholder="e.g. Recurrent networks, LSTMs and attention"
        className={inputClass} />
      <SaveRow count={field.text.length} max={PROJECT_DESCRIPTION_MAX} field={field} buttonLabel="Save description"
        onSave={() => field.save(onSaved)} />
    </div>
  );
}

export function DeleteDialog({ project, busy, onCancel, onConfirm }) {
  const [documents, setDocuments] = useState(null);
  const files = project.document_count ?? 0;
  return (
    <div role="dialog" aria-label={`Delete ${project.name}`} className="mt-3 p-3 rounded-lg border border-destructive/30 bg-destructive/5">
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
