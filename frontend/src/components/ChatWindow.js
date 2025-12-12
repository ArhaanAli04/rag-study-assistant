import { useState, useEffect, useRef } from "react";
import { Menu, Moon, Settings, LogOut, Sparkles } from "lucide-react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatWindow({ sessionId, onSessionCreated }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [showCommentFor, setShowCommentFor] = useState(null);
  const [feedbackComment, setFeedbackComment] = useState('');
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

  // Feedback handler
  const handleFeedback = async (messageId, feedbackType) => {
    const token = localStorage.getItem('token');
    
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
        setShowCommentFor(null);
        setFeedbackComment('');
        
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
    const userMsg = { role: "user", content: query, id: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setStreamingAnswer("");

    const token = localStorage.getItem("token");

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
      if (event.data === "[DONE]") {
        eventSource.close();
        setLoading(false);

        const assistantMsg = {
          role: "assistant",
          content: assistantAnswer,
          id: capturedMessageId || Date.now(),
          sources: metadataReceived?.sources || [],
          confidence: metadataReceived?.confidence || 0,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamingAnswer("");

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
        } else if (data.type === "message_id") {
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

  const handleLogout = () => {
    localStorage.removeItem('token');
    window.location.href = '/login';
  };

  return (
    <div className="flex-1 flex flex-col h-screen">
      {/* Top Navigation */}
      

      {/* Messages Area */}
      <div 
        ref={messagesEndRef} 
        className="flex-1 overflow-y-auto px-4 lg:px-6 py-6" 
        style={{ background: "#0F0F0F" }}
      >
        {messages.length === 0 ? (
          // Empty State
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Sparkles className="w-16 h-16 text-primary mb-4" />
            <h2 className="text-2xl font-semibold mb-2">Start a conversation</h2>
            <p className="text-muted max-w-md">
              Ask me anything about your study materials. I can help explain concepts, summarize documents, and answer questions.
            </p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            <MessageList 
              messages={messages} 
              streamingAnswer={streamingAnswer}
              onFeedback={handleFeedback}
              showCommentFor={showCommentFor}
              feedbackComment={feedbackComment}
              onCommentChange={setFeedbackComment}
              onCancelComment={() => {
                setShowCommentFor(null);
                setFeedbackComment('');
              }}
            />
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
}
