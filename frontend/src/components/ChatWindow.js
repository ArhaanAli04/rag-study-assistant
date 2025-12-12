import { useState, useEffect, useRef } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatWindow({ sessionId, onSessionCreated }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [showCommentFor, setShowCommentFor] = useState(null);  // NEW
  const [feedbackComment, setFeedbackComment] = useState('');   // NEW
  const [assistantMessageId, setAssistantMessageId] = useState(null);  // ← ADD THIS LINE
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

  // NEW: Feedback handler
  const handleFeedback = async (messageId, feedbackType) => {
    const token = localStorage.getItem('token');
    
    // If thumbs down and no comment shown yet, show comment field
    if (feedbackType === 'down' && showCommentFor !== messageId) {
      setShowCommentFor(messageId);
      return;
    }

    try {
      const response = await fetch(`http://localhost:8000/messages/${messageId}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          feedback: feedbackType,
          comment: feedbackType === 'down' ? feedbackComment : '',
        }),
      });

      if (response.ok) {
        console.log('Feedback submitted');
        setShowCommentFor(null);
        setFeedbackComment('');
        
        // Update message to show feedback was submitted
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, userFeedback: feedbackType } 
            : msg
        ));
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    }
  };

  const handleSendMessage = async (query, mode) => {
    // Add user message to UI immediately
    const userMsg = { role: "user", content: query, id: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setStreamingAnswer("");

    const token = localStorage.getItem("token");

    // Pass token as query param for EventSource
    const url = new URL("http://localhost:8000/chat/stream");
    url.searchParams.append("query", query);
    url.searchParams.append("session_id", sessionId || 0);
    url.searchParams.append("top_k", 5);
    url.searchParams.append("mode", mode);
    url.searchParams.append("token", token);

    const eventSource = new EventSource(url.toString());

    let assistantAnswer = "";
    let metadataReceived = null;
    let capturedMessageId = null;

    eventSource.onmessage = (event) => {
      console.log("Received SSE event:", event.data);  // ← ADD THIS
      if (event.data === "[DONE]") {
        console.log("Stream done, message ID:", capturedMessageId);  // ← ADD THIS
        eventSource.close();
        setLoading(false);

        // Add final assistant message
        const assistantMsg = {
          role: "assistant",
          content: assistantAnswer,
          id: capturedMessageId || Date.now(),
          sources: metadataReceived?.sources || [],
          confidence: metadataReceived?.confidence || 0,
        };
        console.log("Creating assistant message with ID:", assistantMsg.id);  // ← ADD THIS
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamingAnswer("");
        setAssistantMessageId(null);  // ← ADD: Reset for next message

        // If new session created, notify parent
        if (metadataReceived?.session_id && !sessionId) {
          onSessionCreated(metadataReceived.session_id);
        }
        return;
      }

      try {
        const data = JSON.parse(event.data);
        console.log("Parsed SSE data:", data);  // ← ADD THIS
        if (data.type === "metadata") {
          metadataReceived = data.data;
        } else if (data.type === "token") {
          assistantAnswer += data.data;
          setStreamingAnswer(assistantAnswer);
        }else if (data.type === "message_id") {  // ← ADD THIS BLOCK
          console.log("Received message_id:", data.data);
          capturedMessageId = data.data;
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
        <MessageList 
          messages={messages} 
          streamingAnswer={streamingAnswer}
          onFeedback={handleFeedback}  // NEW: Pass feedback handler
          showCommentFor={showCommentFor}  // NEW
          feedbackComment={feedbackComment}  // NEW
          onCommentChange={setFeedbackComment}  // NEW
          onCancelComment={() => {  // NEW
            setShowCommentFor(null);
            setFeedbackComment('');
          }}
        />
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
}
