// One project on the Projects page (Day 19): name, description, counts and last activity, with
// rename, archive and delete. Each action keeps its own busy and error state, so a failure shows on
// the card whose control failed.
import { useState } from "react";
import { Archive, ArchiveRestore, Folder, Pencil, Trash2 } from "lucide-react";
import {
  deleteProject,
  lastActivityText,
  projectCounts,
  projectDeletedNotice,
  updateProject,
} from "../services/projectsApi";
import { buttonClass, DeleteDialog, RenameForm } from "./ProjectEditors";

export default function ProjectCard({ project, onChanged }) {
  const [open, setOpen] = useState(null); // null | "rename" | "delete"
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
    <article
      aria-label={`Project ${project.name}`}
      className="glass border border-border/50 rounded-xl p-4 flex flex-col hover:border-primary/50 focus-within:border-primary/50 transition-all"
    >
      <div className="flex items-start gap-3">
        <Folder className={`w-5 h-5 mt-0.5 flex-shrink-0 ${project.archived ? "text-muted-foreground" : "text-primary"}`} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <h3 className="text-sm font-semibold text-foreground truncate">{project.name}</h3>
            {project.archived && (
              <span className="flex-shrink-0 text-xs px-2 py-0.5 rounded-md border border-amber-500/30 text-amber-400">Archived</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {projectCounts(project)} · {lastActivityText(project)}
          </p>
        </div>
      </div>

      {project.description && (
        <p className="text-sm text-muted-foreground mt-3 line-clamp-2 break-words">{project.description}</p>
      )}

      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}

      {open === "rename" && (
        <RenameForm project={project} busy={busy} onCancel={() => setOpen(null)}
          onSave={(name) => run(async () => {
            await updateProject(project.id, { name });
            setOpen(null);
            await onChanged(`Renamed to ${name}.`);
          })} />
      )}
      {open === "delete" && (
        <DeleteDialog project={project} busy={busy} onCancel={() => setOpen(null)}
          onConfirm={(documents) => run(async () => {
            const result = await deleteProject(project.id, documents);
            await onChanged(projectDeletedNotice(project.name, result));
          })} />
      )}

      <div className="flex flex-wrap items-center justify-end gap-1 mt-auto pt-4">
        <button type="button" className={buttonClass} disabled={busy} onClick={() => toggle("rename")}>
          <Pencil className="w-3 h-3" aria-hidden="true" /> Rename
        </button>
        <button type="button" className={buttonClass} disabled={busy} onClick={archive}>
          {project.archived
            ? <><ArchiveRestore className="w-3 h-3" aria-hidden="true" /> Unarchive</>
            : <><Archive className="w-3 h-3" aria-hidden="true" /> Archive</>}
        </button>
        <button type="button" className={`${buttonClass} text-destructive hover:bg-destructive/10`} disabled={busy} onClick={() => toggle("delete")}>
          <Trash2 className="w-3 h-3" aria-hidden="true" /> Delete
        </button>
      </div>
    </article>
  );
}
