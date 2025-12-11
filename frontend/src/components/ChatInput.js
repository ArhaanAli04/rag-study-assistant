import { useState } from "react";

export default function ChatInput({ onSend, disabled }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("quick");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !disabled) {
      onSend(query.trim(), mode);
      setQuery("");
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        padding: "15px 20px",
        backgroundColor: "white",
        borderTop: "1px solid #bdc3c7",
        display: "flex",
        gap: "10px",
        alignItems: "center",
      }}
    >
      {/* Mode selector */}
      <select
        value={mode}
        onChange={(e) => setMode(e.target.value)}
        style={{
          padding: "10px",
          borderRadius: "6px",
          border: "1px solid #bdc3c7",
          backgroundColor: "#ecf0f1",
        }}
      >
        <option value="quick">Quick</option>
        <option value="detailed">Detailed</option>
        <option value="step_by_step">Step-by-Step</option>
      </select>

      {/* Input box */}
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a question..."
        disabled={disabled}
        style={{
          flex: 1,
          padding: "12px",
          borderRadius: "6px",
          border: "1px solid #bdc3c7",
          fontSize: "14px",
        }}
      />

      {/* Send button */}
      <button
        type="submit"
        disabled={disabled || !query.trim()}
        style={{
          padding: "12px 24px",
          backgroundColor: disabled ? "#95a5a6" : "#3498db",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: disabled ? "default" : "pointer",
          fontWeight: "bold",
        }}
      >
        {disabled ? "..." : "Send"}
      </button>
    </form>
  );
}
