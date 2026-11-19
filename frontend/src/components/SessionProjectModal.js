// Move a chat to another project, or to No project (Day 18). The chat's next answer searches there.
import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { activeProjects, listProjects, moveSession } from "../services/projectsApi";

export default function SessionProjectModal({ session, onClose, onMoved }) {
  const [projects, setProjects] = useState([]);
  const [loadState, setLoadState] = useState("loading"); // loading | ready | error
  const [loadError, setLoadError] = useState(null);
  const current = session.project_id === null || session.project_id === undefined ? "" : String(session.project_id);
  const [target, setTarget] = useState(current);
  const [moving, setMoving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (cancelled) return;
        setProjects(activeProjects(data));
        setLoadState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err.message);
        setLoadState("error");
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const handleEscape = (e) => { if (e.key === "Escape" && !moving) onClose(); };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose, moving]);

  const handleMove = async (e) => {
    e.preventDefault();
    setMoving(true);
    setError(null);
    try {
      await moveSession(session.id, target === "" ? null : Number(target));
      await onMoved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setMoving(false);
    }
  };

  const title = session.title || `Session ${session.id}`;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[10000] p-4" onClick={() => !moving && onClose()}>
      <div role="dialog" aria-label={`Move ${title} to a project`}
        className="bg-[#1F2937] border border-[#374151] rounded-xl p-6 max-w-md w-full shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Move to project</h3>
          <button type="button" onClick={onClose} disabled={moving} aria-label="Close"
            className="p-1 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          “{title}” will answer only from the chosen project's files from its next message on.
        </p>

        {loadState === "loading" ? (
          <div role="status" className="flex items-center gap-2 text-sm text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Loading projects…
          </div>
        ) : loadState === "error" ? (
          <p role="alert" className="text-sm text-red-400">Couldn't load your projects: {loadError}</p>
        ) : (
          <form onSubmit={handleMove}>
            {projects.length === 0 && (
              <p className="text-sm text-gray-400 mb-3">
                No projects yet. Create one on the Documents page; until then a chat can only be in No project.
              </p>
            )}
            <label htmlFor="session-project" className="block text-sm text-gray-400 mb-2">Project</label>
            <select id="session-project" value={target} disabled={moving} onChange={(e) => setTarget(e.target.value)}
              className="w-full px-4 py-3 bg-[#111827] border border-[#374151] rounded-lg text-white">
              <option value="">No project</option>
              {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
            </select>
            {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
            <div className="flex gap-3 mt-4">
              <button type="button" onClick={onClose} disabled={moving}
                className="flex-1 px-4 py-2.5 bg-[#374151] text-white rounded-lg font-medium">Cancel</button>
              <button type="submit" disabled={moving || target === current}
                className="flex-1 px-4 py-2.5 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium disabled:opacity-50">
                {moving ? "Moving…" : "Move chat"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
