import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import LoginForm from "../components/LoginForm";
import {
  accountDeletedNotice,
  forgetAccountDeletion,
  readAccountDeletion,
} from "../utils/accountDeletion";

export default function LoginPage() {
  const { login } = useAuth();
  const [error, setError] = useState("");
  const [notice] = useState(() => accountDeletedNotice(readAccountDeletion()));
  const navigate = useNavigate();

  // Removed in an effect, not in the state initializer: StrictMode runs initializers twice, and
  // a read-and-remove there would hand the second run nothing.
  useEffect(() => {
    forgetAccountDeletion();
  }, []);

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

  return <LoginForm onSubmit={handleLogin} error={error} notice={notice} />;
}
