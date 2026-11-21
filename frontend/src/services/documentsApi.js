// Document uploads and deletes (Day 19: shared by the Documents page and a project's page).
// Both throw an Error carrying the server's `detail`, so callers show it as is.
import { API_BASE_URL } from "../config/api";

function authHeader() {
  return { Authorization: `Bearer ${localStorage.getItem("token")}` };
}

async function errorDetail(response, fallback) {
  const body = await response.json().catch(() => ({}));
  return body.detail || fallback;
}

// projectId: a project's id, or "" / null for No project. Resolves to the upload result
// (status new / changed / unchanged / reindexed), which uploadNotice() turns into a message.
export async function uploadDocument(file, projectId) {
  const formData = new FormData();
  formData.append("file", file);
  if (projectId) {
    formData.append("project_id", String(projectId));
  }
  // No Content-Type header: the browser sets the multipart boundary itself.
  const response = await fetch(`${API_BASE_URL}/upload`, { method: "POST", headers: authHeader(), body: formData });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Upload failed"));
  }
  return response.json();
}

// Deletes every version of the document; resolves to { versions_deleted, … }.
export async function deleteDocument(documentId) {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, { method: "DELETE", headers: authHeader() });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to delete document"));
  }
  return response.json();
}
