import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import SessionSidebar from "../components/SessionSidebar";
import ChatWindow from "../components/ChatWindow";
import TopNav from "../components/TopNav";

export default function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Fetch sessions on mount
  useEffect(() => {
    fetchSessions();
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const fetchSessions = async () => {
    try {
        const token = localStorage.getItem("token");
        const resp = await fetch("http://localhost:8000/sessions", {
        headers: { Authorization: `Bearer ${token}` },
        });
        
        if (!resp.ok) {
        console.error("Failed to fetch sessions:", resp.status);
        setSessions([]);  // Set empty array on error
        return;
        }
        
        const data = await resp.json();
        setSessions(Array.isArray(data) ? data : []);  // Ensure it's an array
    } catch (e) {
        console.error("Failed to fetch sessions:", e);
        setSessions([]);  // Set empty array on error
    }
    };

  const handleNewChat = () => {
    setActiveSessionId(null); // null = new session
  };

  const handleSessionCreated = (newSessionId) => {
    setActiveSessionId(newSessionId);
    fetchSessions(); // refresh sidebar
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Top Navigation */}
      <TopNav user={user} onLogout={handleLogout} onToggleSidebar={() => setSidebarOpen(!sidebarOpen)} />

      {/* Main area: Sidebar + Chat */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {sidebarOpen && (
          <SessionSidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={setActiveSessionId}
            onNewChat={handleNewChat}
          />
        )}
        <ChatWindow
          sessionId={activeSessionId}
          onSessionCreated={handleSessionCreated}
        />
      </div>
    </div>
  );
}
