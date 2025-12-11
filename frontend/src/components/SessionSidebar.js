export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
}) {
  return (
    <div
      style={{
        width: "280px",
        backgroundColor: "#34495e",
        color: "white",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* New Chat Button */}
      <div style={{ padding: "15px", borderBottom: "1px solid #2c3e50" }}>
        <button
          onClick={onNewChat}
          style={{
            width: "100%",
            padding: "12px",
            backgroundColor: "#3498db",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          + New Chat
        </button>
      </div>

      {/* Session List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px" }}>
        {sessions.length === 0 && (
          <p style={{ textAlign: "center", color: "#95a5a6" }}>No sessions yet</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.id}
            onClick={() => onSelectSession(session.id)}
            style={{
              padding: "12px",
              marginBottom: "8px",
              backgroundColor: activeSessionId === session.id ? "#2c3e50" : "#2c3e50aa",
              borderRadius: "6px",
              cursor: "pointer",
              transition: "background 0.2s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#2c3e50")}
            onMouseLeave={(e) =>
              (e.currentTarget.style.backgroundColor =
                activeSessionId === session.id ? "#2c3e50" : "#2c3e50aa")
            }
          >
            <div style={{ fontSize: "14px", fontWeight: "500" }}>
              {session.title || `Session ${session.id}`}
            </div>
            <div style={{ fontSize: "11px", color: "#95a5a6", marginTop: "4px" }}>
              {new Date(session.created_at).toLocaleDateString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
