import { useState, useEffect, useCallback } from "react";
import { apiRequest } from "../services/apiClient";
import { API_BASE_URL } from '../config/api';

export function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (token) {
      setUser({ email: "user" });
    } else {
      setUser(null);
    }
  }, [token]);

  const login = useCallback(async (email, password) => {
    // LOGIN USES FORM DATA, NOT JSON
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const resp = await fetch(`${API_BASE_URL}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData.toString(),
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || "Login failed");
    }

    localStorage.setItem("token", data.access_token);
    setToken(data.access_token);

    // Wait for state to update
    await new Promise(resolve => setTimeout(resolve, 50));
    return data;
  }, []);

  const register = useCallback(async (email, password) => {
    const data = await apiRequest("/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  }, []);

  return { token, user, login, register, logout, isAuthenticated: !!token };
}
