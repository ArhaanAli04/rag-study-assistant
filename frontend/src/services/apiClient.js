const API_BASE = "http://localhost:8000";

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

  const resp = await fetch(`${API_BASE}${path}`, {
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
