import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import QuizPage from "./pages/QuizPage";
import ConceptMapPage from "./pages/ConceptMapPage";
import AuthCallback from "./pages/AuthCallback";

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

       {/* ← ADD OAUTH CALLBACK ROUTE */}
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route
        path="/chat"
        element={isAuthenticated ? <ChatPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/documents"
        element={isAuthenticated ? <DocumentsPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/quiz"
        element={isAuthenticated ? <QuizPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/concept-maps"
        element={isAuthenticated ? <ConceptMapPage /> : <Navigate to="/login" replace />}
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}
