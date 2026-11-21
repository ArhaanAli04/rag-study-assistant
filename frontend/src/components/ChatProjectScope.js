// The chat header's project line (Day 18): which project a chat belongs to, or "No project", and
// what its answers can cite. A new chat shows a picker instead; the choice is fixed by its first
// message (moving it later is the sidebar's "Move to project"). Day 19: the project's name links to
// its page, and `note` explains a preselection that fell back to No project.
import { Link } from "react-router-dom";
import { Folder, Loader2 } from "lucide-react";
import { scopeDescription } from "../services/projectsApi";

const linkClass = "hover:text-white hover:underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60";

function ProjectLabel({ projectName, projectId }) {
  if (!projectName) return "No project";
  return (
    <>
      Project:{" "}
      {projectId ? <Link to={`/projects/${projectId}`} className={linkClass}>{projectName}</Link> : projectName}
    </>
  );
}

export default function ChatProjectScope({
  isNewChat,
  projectName,
  projectId = null,
  projects,
  projectsState, // loading | ready | error
  selectedProjectId,
  onSelect,
  locked,
  note = null,
}) {
  if (!isNewChat) {
    return (
      <div className="flex flex-col" data-testid="chat-project">
        <span className="inline-flex items-center gap-1 text-xs text-gray-300">
          <Folder className="w-3 h-3" aria-hidden="true" />
          <ProjectLabel projectName={projectName} projectId={projectId} />
        </span>
        <span className="text-xs text-gray-500">{scopeDescription(projectName)}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col" data-testid="chat-project">
      <div className="flex items-center gap-2">
        <label htmlFor="new-chat-project" className="text-xs text-gray-300">Project</label>
        {projectsState === "loading" ? (
          <span role="status" className="inline-flex items-center gap-1 text-xs text-gray-400">
            <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" /> Loading projects…
          </span>
        ) : (
          <select
            id="new-chat-project"
            value={selectedProjectId}
            disabled={locked}
            onChange={(e) => onSelect(e.target.value)}
            className="px-2 py-1 bg-[#111827] border border-[#374151] rounded-md text-xs text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <option value="">No project</option>
            {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
          </select>
        )}
        {projectId && projectName && (
          <Link to={`/projects/${projectId}`} className={`text-xs text-gray-400 ${linkClass}`}>Open project</Link>
        )}
      </div>
      {projectsState === "error" ? (
        <span role="alert" className="text-xs text-amber-400">
          Couldn't load your projects, so this chat will use No project.
        </span>
      ) : note ? (
        <span role="alert" className="text-xs text-amber-400">{note}</span>
      ) : (
        <span className="text-xs text-gray-500">{scopeDescription(projectName)}</span>
      )}
    </div>
  );
}
