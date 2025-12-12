import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import LoginForm from "../components/LoginForm";

export default function LoginPage() {
  const { login } = useAuth();
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleLogin = async (email, password) => {
    try {
      setError("");
      console.log("Attempting login...");
      await login(email, password);
      console.log("Login successful, navigating to /chat");
      navigate("/chat");
    } catch (e) {
      console.error("Login error:", e);
      setError(e.message || "Login failed");
    }
  };

  return <LoginForm onSubmit={handleLogin} error={error} />;
}
