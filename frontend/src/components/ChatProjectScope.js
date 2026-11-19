// The chat header's project line (Day 18): which project a chat belongs to, or "No project", and
// what its answers can cite. A new chat shows a picker instead; the choice is fixed by its first
// message (moving it later is the sidebar's "Move to project").
import { Folder, Loader2 } from "lucide-react";
import { scopeDescription } from "../services/projectsApi";

export default function ChatProjectScope({
  isNewChat,
  projectName,
  projects,
  projectsState, // loading | ready | error
  selectedProjectId,
  onSelect,
  locked,
}) {
  if (!isNewChat) {
    return (
      <div className="flex flex-col" data-testid="chat-project">
        <span className="inline-flex items-center gap-1 text-xs text-gray-300">
          <Folder className="w-3 h-3" aria-hidden="true" />
          {projectName ? `Project: ${projectName}` : "No project"}
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
            className="px-2 py-1 bg-[#111827] border border-[#374151] rounded-md text-xs text-white"
          >
            <option value="">No project</option>
            {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
          </select>
        )}
      </div>
      {projectsState === "error" ? (
        <span role="alert" className="text-xs text-amber-400">
          Couldn't load your projects, so this chat will use No project.
        </span>
      ) : (
        <span className="text-xs text-gray-500">{scopeDescription(projectName)}</span>
      )}
    </div>
  );
}
