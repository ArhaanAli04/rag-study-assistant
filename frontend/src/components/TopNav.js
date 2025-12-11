export default function TopNav({ user, onLogout, onToggleSidebar }) {
  return (
    <div
      style={{
        height: "60px",
        backgroundColor: "#2c3e50",
        color: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "15px" }}>
        <button
          onClick={onToggleSidebar}
          style={{
            background: "transparent",
            border: "none",
            color: "white",
            fontSize: "20px",
            cursor: "pointer",
          }}
        >
          ☰
        </button>
        <h1 style={{ margin: 0, fontSize: "20px" }}>RAG Study Assistant</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "15px" }}>
        <span>{user?.email || "User"}</span>
        <button
          onClick={onLogout}
          style={{
            padding: "8px 16px",
            backgroundColor: "#e74c3c",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          Logout
        </button>
      </div>
    </div>
  );
}
