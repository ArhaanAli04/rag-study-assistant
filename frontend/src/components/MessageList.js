import MessageBubble from "./MessageBubble";

export default function MessageList({ 
  messages, 
  streamingAnswer,
  onFeedback,  // NEW
  showCommentFor,  // NEW
  feedbackComment,  // NEW
  onCommentChange,  // NEW
  onCancelComment  // NEW
}) {
  return (
    <>
      {messages.map((msg, idx) => (
        <div
          key={idx}
          style={{
            marginBottom: "15px",
            textAlign: msg.role === "user" ? "right" : "left",
          }}
        >
          <div
            style={{
              display: "inline-block",
              maxWidth: "70%",
              padding: "12px",
              borderRadius: "8px",
              backgroundColor: msg.role === "user" ? "#3498db" : "#fff",
              color: msg.role === "user" ? "#fff" : "#2c3e50",
              textAlign: "left",
              boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
            }}
          >
            {msg.content}
          </div>

          {/* NEW: Feedback buttons for assistant messages */}
          {msg.role === 'assistant' && msg.id && (
            <div style={{ marginTop: "8px", display: "inline-block" }}>
              <button
                onClick={() => onFeedback(msg.id, 'up')}
                disabled={msg.userFeedback}
                style={{
                  background: msg.userFeedback === 'up' ? '#007bff' : 'none',
                  border: '1px solid #ddd',
                  padding: '4px 8px',
                  cursor: msg.userFeedback ? 'not-allowed' : 'pointer',
                  borderRadius: '4px',
                  marginRight: '8px',
                  fontSize: '16px',
                  opacity: msg.userFeedback ? 0.5 : 1,
                }}
              >
                👍
              </button>
              <button
                onClick={() => onFeedback(msg.id, 'down')}
                disabled={msg.userFeedback}
                style={{
                  background: msg.userFeedback === 'down' ? '#dc3545' : 'none',
                  border: '1px solid #ddd',
                  padding: '4px 8px',
                  cursor: msg.userFeedback ? 'not-allowed' : 'pointer',
                  borderRadius: '4px',
                  fontSize: '16px',
                  opacity: msg.userFeedback ? 0.5 : 1,
                }}
              >
                👎
              </button>

              {/* NEW: Comment field appears when thumbs down clicked */}
              {showCommentFor === msg.id && (
                <div style={{
                  marginTop: '10px',
                  padding: '10px',
                  background: '#f8f9fa',
                  borderRadius: '4px',
                  maxWidth: '400px'
                }}>
                  <textarea
                    placeholder="What went wrong? (optional)"
                    value={feedbackComment}
                    onChange={(e) => onCommentChange(e.target.value)}
                    rows={3}
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px',
                      fontFamily: 'inherit',
                      resize: 'vertical'
                    }}
                  />
                  <div style={{ marginTop: '8px', display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => onFeedback(msg.id, 'down')}
                      style={{
                        padding: '6px 16px',
                        background: '#007bff',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '14px'
                      }}
                    >
                      Submit
                    </button>
                    <button
                      onClick={onCancelComment}
                      style={{
                        padding: '6px 16px',
                        background: '#6c757d',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '14px'
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* Streaming answer */}
      {streamingAnswer && (
        <div style={{ marginBottom: "15px", textAlign: "left" }}>
          <div
            style={{
              display: "inline-block",
              maxWidth: "70%",
              padding: "12px",
              borderRadius: "8px",
              backgroundColor: "#fff",
              color: "#2c3e50",
              textAlign: "left",
              boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
            }}
          >
            {streamingAnswer}
            <span className="cursor">▊</span>
          </div>
        </div>
      )}
    </>
  );
}

