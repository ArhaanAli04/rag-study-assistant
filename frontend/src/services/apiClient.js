import { API_BASE_URL } from "../config/api";

function getToken() {
  return localStorage.getItem("token");
}

export async function apiRequest(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  const data = await resp.json().catch(() => ({}));

  if (!resp.ok) {
    const message = data.detail || "Request failed";
    throw new Error(message);
  }

  return data;
}
