import { useState } from "react";
import { API_BASE_URL } from '../config/api';

export default function MessageBubble({ message }) {
  const [feedback, setFeedback] = useState(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");

  const isUser = message.role === "user";

  const handleFeedback = async (type) => {
    setFeedback(type);
    if (type === "down") {
      setShowComment(true);
    } else {
      await sendFeedback(type, "");
    }
  };

  const sendFeedback = async (type, commentText) => {
    try {
      const token = localStorage.getItem("token");
      await fetch(`${API_BASE_URL}/messages/${message.id}/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ feedback: type, comment: commentText }),
      });
      console.log("Feedback sent:", type);
    } catch (e) {
      console.error("Failed to send feedback:", e);
    }
  };

  const submitComment = () => {
    sendFeedback(feedback, comment);
    setShowComment(false);
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: "15px",
      }}
    >
      <div
        style={{
          maxWidth: "70%",
          padding: "12px 16px",
          borderRadius: "12px",
          backgroundColor: isUser ? "#3498db" : "#ffffff",
          color: isUser ? "white" : "#2c3e50",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div style={{ marginTop: "10px", fontSize: "12px", color: "#7f8c8d" }}>
            <strong>Sources:</strong>
            {message.sources.slice(0, 3).map((src, i) => (
              <div key={i}>
                {src.file_name || src.url || "Unknown"}
                {src.page_num && ` (Page ${src.page_num})`}
              </div>
            ))}
          </div>
        )}

        {/* Feedback buttons (assistant only, not streaming) */}
        {!isUser && !message.streaming && message.id && (
          <div style={{ marginTop: "10px", display: "flex", gap: "10px" }}>
            <button
              onClick={() => handleFeedback("up")}
              disabled={feedback !== null}
              style={{
                background: feedback === "up" ? "#27ae60" : "#ecf0f1",
                border: "none",
                padding: "6px 12px",
                borderRadius: "4px",
                cursor: feedback ? "default" : "pointer",
              }}
            >
              👍
            </button>
            <button
              onClick={() => handleFeedback("down")}
              disabled={feedback !== null}
              style={{
                background: feedback === "down" ? "#e74c3c" : "#ecf0f1",
                border: "none",
                padding: "6px 12px",
                borderRadius: "4px",
                cursor: feedback ? "default" : "pointer",
              }}
            >
              👎
            </button>
          </div>
        )}

        {/* Comment input (if downvoted) */}
        {showComment && (
          <div style={{ marginTop: "10px" }}>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="What went wrong? (optional)"
              style={{ width: "100%", padding: "8px", borderRadius: "4px" }}
            />
            <button
              onClick={submitComment}
              style={{
                marginTop: "5px",
                padding: "6px 12px",
                backgroundColor: "#3498db",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              Submit
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
