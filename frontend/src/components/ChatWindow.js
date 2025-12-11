import { useState, useEffect, useRef } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatWindow({ sessionId, onSessionCreated }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const messagesEndRef = useRef(null);

  // Fetch messages when session changes
  useEffect(() => {
    if (sessionId) {
      fetchMessages(sessionId);
    } else {
      setMessages([]);
    }
  }, [sessionId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingAnswer]);

  const fetchMessages = async (sid) => {
    try {
      const token = localStorage.getItem("token");
      const resp = await fetch(`http://localhost:8000/sessions/${sid}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json();
      setMessages(data || []);
    } catch (e) {
      console.error("Failed to fetch messages:", e);
    }
  };

  const handleSendMessage = async (query, mode) => {
    // Add user message to UI immediately
    const userMsg = { role: "user", content: query, id: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setStreamingAnswer("");

    const token = localStorage.getItem("token");

    // NEW: Pass token as query param for EventSource
    const url = new URL("http://localhost:8000/chat/stream");
    url.searchParams.append("query", query);
    url.searchParams.append("session_id", sessionId || 0);
    url.searchParams.append("top_k", 5);
    url.searchParams.append("mode", mode);
    url.searchParams.append("token", token);  // NEW

    const eventSource = new EventSource(url.toString());

    let assistantAnswer = "";
    let metadataReceived = null;

    eventSource.onmessage = (event) => {
      if (event.data === "[DONE]") {
        eventSource.close();
        setLoading(false);

        // Add final assistant message
        const assistantMsg = {
          role: "assistant",
          content: assistantAnswer,
          id: metadataReceived?.session_id || Date.now(),
          sources: metadataReceived?.sources || [],
          confidence: metadataReceived?.confidence || 0,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamingAnswer("");

        // If new session created, notify parent
        if (metadataReceived?.session_id && !sessionId) {
          onSessionCreated(metadataReceived.session_id);
        }
        return;
      }

      try {
        const data = JSON.parse(event.data);
        if (data.type === "metadata") {
          metadataReceived = data.data;
        } else if (data.type === "token") {
          assistantAnswer += data.data;
          setStreamingAnswer(assistantAnswer);
        }
      } catch (e) {
        console.error("Failed to parse SSE data:", e);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE error:", err);
      eventSource.close();
      setLoading(false);
      setStreamingAnswer("");
    };
  };

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#ecf0f1",
      }}
    >
      {/* Messages area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        <MessageList messages={messages} streamingAnswer={streamingAnswer} />
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
}
