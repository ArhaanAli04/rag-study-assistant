// /projects (Day 19): every project as a card, a create form, and the archived ones apart.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, FolderKanban, FolderPlus, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import ProjectCard from "../components/ProjectCard";
import { focusRing, inputClass } from "../components/ProjectEditors";
import { createProject, listProjects, PROJECT_DESCRIPTION_MAX, PROJECT_NAME_MAX } from "../services/projectsApi";

const gridClass = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4";

export default function ProjectsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [showArchived, setShowArchived] = useState(false);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listProjects();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // After any change: say what happened and refetch, so counts and last activity stay the server's.
  const handleChanged = async (message) => {
    setNotice(message);
    await fetchProjects();
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const active = projects.filter((p) => !p.archived);
  const archived = projects.filter((p) => p.archived);

  return (
    <div className="flex flex-col h-screen" style={{ background: "#0F0F0F" }}>
      <TopNav user={user} onLogout={handleLogout} onToggleSidebar={() => {}} />

      <main className="flex-1 overflow-y-auto px-4 lg:px-8 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent mb-2">
              Projects
            </h1>
            <p className="text-muted-foreground">
              One project per course: its files, its instructions and its chats. A chat in a project answers only from that project's files.
            </p>
          </div>

          {notice && (
            <div role="status" className="mb-6 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <p className="text-sm text-emerald-300">{notice}</p>
            </div>
          )}

          <CreateProjectForm onCreated={(created) => handleChanged(`Created project ${created.name}.`)} />

          {loading ? (
            <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" /> Loading projects…
            </div>
          ) : error ? (
            <div role="alert" className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex flex-wrap items-center gap-3">
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0" aria-hidden="true" />
              <span className="text-sm text-destructive">Couldn't load your projects: {error}</span>
              <button type="button" onClick={fetchProjects} className={`text-sm text-destructive underline rounded ${focusRing}`}>
                Try again
              </button>
            </div>
          ) : projects.length === 0 ? (
            <div className="text-center py-12 glass border border-border/50 rounded-2xl">
              <FolderKanban className="w-16 h-16 text-muted-foreground/40 mx-auto mb-4" aria-hidden="true" />
              <h2 className="text-lg font-medium text-foreground mb-2">Create your first project</h2>
              <p className="text-sm text-muted-foreground">
                Make one per course, e.g. “DL Unit 5”, then upload its files into it.
              </p>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold text-foreground mb-4">Your projects ({active.length})</h2>
              {active.length === 0 ? (
                <p className="py-6 text-sm text-muted-foreground">Every project is archived. Unarchive one, or create a new one.</p>
              ) : (
                <div className={gridClass}>
                  {active.map((p) => <ProjectCard key={p.id} project={p} onChanged={handleChanged} />)}
                </div>
              )}

              {archived.length > 0 && (
                <section className="mt-10">
                  <button
                    type="button"
                    onClick={() => setShowArchived(!showArchived)}
                    aria-expanded={showArchived}
                    className={`flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground rounded transition-colors ${focusRing}`}
                  >
                    {showArchived ? <ChevronDown className="w-4 h-4" aria-hidden="true" /> : <ChevronRight className="w-4 h-4" aria-hidden="true" />}
                    Archived ({archived.length})
                  </button>
                  {showArchived && (
                    <div className={`${gridClass} mt-4`}>
                      {archived.map((p) => <ProjectCard key={p.id} project={p} onChanged={handleChanged} />)}
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function CreateProjectForm({ onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Give the project a name.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const fields = { name: trimmed };
      if (description.trim()) fields.description = description.trim();
      const created = await createProject(fields);
      setName("");
      setDescription("");
      await onCreated(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} aria-labelledby="new-project-heading" className="glass border border-border/50 rounded-2xl p-6 mb-8">
      <h2 id="new-project-heading" className="text-lg font-semibold text-foreground mb-4">New project</h2>
      <div className="grid gap-3 md:grid-cols-[1fr_2fr]">
        <div>
          <label htmlFor="new-project-name" className="block text-xs text-muted-foreground mb-1">
            Name ({name.length} / {PROJECT_NAME_MAX})
          </label>
          <input id="new-project-name" value={name} maxLength={PROJECT_NAME_MAX} disabled={creating}
            onChange={(e) => { setName(e.target.value); setError(null); }}
            placeholder="e.g. DL Unit 5" className={inputClass} />
        </div>
        <div>
          <label htmlFor="new-project-description" className="block text-xs text-muted-foreground mb-1">
            Description, optional ({description.length} / {PROJECT_DESCRIPTION_MAX})
          </label>
          <input id="new-project-description" value={description} maxLength={PROJECT_DESCRIPTION_MAX} disabled={creating}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What the course covers" className={inputClass} />
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-destructive mt-3">{error}</p>}
      <div className="flex justify-end mt-4">
        <button
          type="submit"
          disabled={creating}
          className={`inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg text-sm font-medium hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed ${focusRing}`}
        >
          <FolderPlus className="w-4 h-4" aria-hidden="true" />
          {creating ? "Creating…" : "Create project"}
        </button>
      </div>
    </form>
  );
}
