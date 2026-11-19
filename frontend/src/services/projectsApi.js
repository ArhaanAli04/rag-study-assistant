// Projects API (Day 18). Every call goes through apiRequest, which adds the token and turns a
// non-2xx reply into an Error carrying the server's `detail` (e.g. 409 "You already have a project
// named …"), so callers can show it as is.
import { apiRequest } from "./apiClient";

// Limits the backend enforces (app/db/models/project.py); the UI shows them before the server must.
export const PROJECT_NAME_MAX = 80;
export const PROJECT_DESCRIPTION_MAX = 500;
export const PROJECT_INSTRUCTIONS_MAX = 4000;

export function listProjects() {
  return apiRequest("/projects");
}

export function getProject(projectId) {
  return apiRequest(`/projects/${projectId}`);
}

export function createProject(fields) {
  return apiRequest("/projects", { method: "POST", body: JSON.stringify(fields) });
}

// Only the fields passed change; `archived: true|false` archives or unarchives.
export function updateProject(projectId, changes) {
  return apiRequest(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(changes) });
}

// documents: "delete" (its files go too) or "unassign" (they move to No project). Its chats always
// move to No project.
export function deleteProject(projectId, documents) {
  return apiRequest(`/projects/${projectId}?documents=${encodeURIComponent(documents)}`, { method: "DELETE" });
}

// projectId null = No project.
export function moveDocument(documentId, projectId) {
  return apiRequest(`/documents/${documentId}`, { method: "PATCH", body: JSON.stringify({ project_id: projectId }) });
}

export function moveSession(sessionId, projectId) {
  return apiRequest(`/sessions/${sessionId}/project`, {
    method: "PATCH",
    body: JSON.stringify({ project_id: projectId }),
  });
}

// Pickers offer only projects that take new files and chats.
export function activeProjects(projects) {
  return Array.isArray(projects) ? projects.filter((p) => !p.archived) : [];
}

export const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function projectCounts(project) {
  return `${plural(project.document_count ?? 0, "file")} · ${plural(project.chat_count ?? 0, "chat")}`;
}

export function projectDeletedNotice(name, result) {
  const chats = result.chats_unassigned
    ? ` Its ${plural(result.chats_unassigned, "chat")} moved to No project.`
    : "";
  if (result.documents === "delete") {
    return `Deleted project ${name} and ${plural(result.documents_deleted ?? 0, "file")}.${chats}`;
  }
  return `Deleted project ${name}. ${plural(result.documents_unassigned ?? 0, "file")} moved to No project.${chats}`;
}

// What a chat in this scope may cite, for the chat header (Day 18, Decision 1A).
export function scopeDescription(projectName) {
  return projectName
    ? `Answers cite only files in ${projectName}.`
    : "No project: answers cite only documents that aren't in a project.";
}
