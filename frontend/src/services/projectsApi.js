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

// The backend sends naive UTC times ("2026-11-19T10:00:00"); new Date() would read those as local
// time, which is off by the browser's UTC offset (5h30 in India), so mark them as UTC first.
export function parseServerTime(value) {
  if (!value) return null;
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function formatShortDate(date, now = new Date()) {
  const options = { month: "short", day: "numeric" };
  if (date.getFullYear() !== now.getFullYear()) options.year = "numeric";
  return date.toLocaleDateString("en-US", options);
}

export function formatRelativeTime(date, now = new Date()) {
  const elapsed = now - date;
  if (elapsed < MINUTE) return "just now";
  if (elapsed < HOUR) return plural(Math.floor(elapsed / MINUTE), "minute") + " ago";
  if (elapsed < DAY) return plural(Math.floor(elapsed / HOUR), "hour") + " ago";
  if (elapsed < 2 * DAY) return "yesterday";
  if (elapsed < 7 * DAY) return `${Math.floor(elapsed / DAY)} days ago`;
  return formatShortDate(date, now);
}

// last_activity is the newer of the newest message and the newest upload (Day 19), so it is empty
// only for a project with neither; a project with chats but no messages falls back to its creation.
export function lastActivityText(project, now = new Date()) {
  const last = parseServerTime(project.last_activity);
  if (last) return `Active ${formatRelativeTime(last, now)}`;
  if (!project.document_count && !project.chat_count) return "No activity yet";
  const created = parseServerTime(project.created_at);
  return created ? `Created ${formatShortDate(created, now)}` : "No activity yet";
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
