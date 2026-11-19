// The Documents page's Projects panel (Day 18): create, list, and manage projects. Day 19 moves
// these controls onto dedicated /projects pages.
import { useState } from "react";
import { AlertCircle, FolderPlus, Loader2 } from "lucide-react";
import ProjectRow from "./ProjectRow";
import { createProject, PROJECT_NAME_MAX } from "../services/projectsApi";

export default function ProjectPanel({ projects, loading, error, onRetry, onChanged }) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  const handleCreate = async (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setCreateError("Give the project a name.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createProject({ name: trimmed });
      setName("");
      await onChanged(`Created project ${created.name}.`);
    } catch (err) {
      setCreateError(err.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <section aria-labelledby="projects-heading" className="glass border border-border/50 rounded-2xl p-6 mb-8">
      <h3 id="projects-heading" className="text-lg font-semibold text-foreground mb-1">Projects</h3>
      <p className="text-sm text-muted-foreground mb-4">
        One project per course: a chat in a project answers only from that project's files.
      </p>

      <form onSubmit={handleCreate} className="flex gap-2 mb-2">
        <label htmlFor="new-project-name" className="sr-only">New project name</label>
        <input
          id="new-project-name"
          value={name}
          onChange={(e) => { setName(e.target.value); setCreateError(null); }}
          maxLength={PROJECT_NAME_MAX}
          placeholder="New project, e.g. DL Unit 5"
          disabled={creating}
          className="flex-1 px-3 py-2 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          disabled={creating}
          className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg text-sm font-medium disabled:opacity-50"
        >
          <FolderPlus className="w-4 h-4" aria-hidden="true" />
          {creating ? "Creating…" : "Create project"}
        </button>
      </form>
      {createError && <p role="alert" className="text-sm text-destructive mb-2">{createError}</p>}

      {loading ? (
        <div role="status" className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Loading projects…
        </div>
      ) : error ? (
        <div role="alert" className="flex items-center gap-3 py-4 text-sm text-destructive">
          <AlertCircle className="w-4 h-4" aria-hidden="true" />
          <span>Couldn't load your projects: {error}</span>
          <button type="button" onClick={onRetry} className="underline">Try again</button>
        </div>
      ) : projects.length === 0 ? (
        <p className="py-4 text-sm text-muted-foreground">
          No projects yet. Create one per course, e.g. “DL Unit 5”, then upload its files into it.
        </p>
      ) : (
        <ul className="divide-y divide-border/50 mt-2">
          {projects.map((project) => (
            <ProjectRow key={project.id} project={project} onChanged={onChanged} />
          ))}
        </ul>
      )}
    </section>
  );
}
