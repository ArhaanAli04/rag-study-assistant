import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import RegisterForm from "../components/RegisterForm";

export default function RegisterPage() {
  const { register } = useAuth();
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleRegister = async (email, password) => {
    try {
      setError("");
      await register(email, password);
      navigate("/login");
    } catch (e) {
      setError(e.message || "Registration failed");
    }
  };

  return <RegisterForm onSubmit={handleRegister} error={error} />;
}
