import { useState, useEffect, useRef } from "react";
import { Sparkles, Download } from "lucide-react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import { exportChatAsMarkdown, exportChatAsPDF } from "../utils/exportUtils";
import ExportChatMenu from "./ExportChatMenu";
import { API_BASE_URL } from '../config/api';

export default function ChatWindow({ sessionId, onSessionCreated }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [showCommentFor, setShowCommentFor] = useState(null);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [sessionTitle, setSessionTitle] = useState("Chat Export");
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  // Fetch messages when session changes
  useEffect(() => {
    if (sessionId) {
      fetchMessages(sessionId);
    } else {
      setMessages([]);
      setSessionTitle("Chat Export");
    }
  }, [sessionId]);

  // DISABLED Auto-scroll - This was causing the issue
  // useEffect(() => {
  //   messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  // }, [messages, streamingAnswer]);

  const fetchMessages = async (sid) => {
    try {
      const token = localStorage.getItem("token");
      
      // Fetch session info to get title
      const sessionResp = await fetch(`${API_BASE_URL}/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (sessionResp.ok) {
        const sessions = await sessionResp.json();
        const currentSession = sessions.find(s => s.id === sid);
        if (currentSession) {
          setSessionTitle(currentSession.title || `Session ${sid}`);
        }
      }
      
      // Fetch messages
      const resp = await fetch(`${API_BASE_URL}/sessions/${sid}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (!resp.ok) {
        throw new Error(`Failed to fetch messages: ${resp.status}`);
      }
      
      const data = await resp.json();
      setMessages(data || []);
    } catch (e) {
      console.error("Failed to fetch messages:", e);
      
      if (sid) {
        const errorMsg = {
          role: "assistant",
          content: "⚠️ Unable to load previous messages. Please refresh the page.",
          id: Date.now(),
          isError: true,
        };
        setMessages([errorMsg]);
      }
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
      const response = await fetch(`${API_BASE_URL}/messages/${messageId}/feedback`, {
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
      } else {
        console.error('Feedback failed:', response.status);
        alert('Failed to submit feedback. Please try again.');
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      alert('Failed to submit feedback. Please check your connection.');
    }
  };

  const handleSendMessage = async (query, mode) => {
    const userMsg = { role: "user", content: query, id: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setStreamingAnswer("");

    const token = localStorage.getItem("token");

    const url = new URL("/chat/stream",API_BASE_URL);
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
        } 
        else if (data.type === "token") {
          assistantAnswer += data.data;
          setStreamingAnswer(assistantAnswer);
        } 
        else if (data.type === "message_id") {
          capturedMessageId = data.data;
        } 
        else if (data.type === "error") {
          eventSource.close();
          setLoading(false);
          setStreamingAnswer("");
          
          const errorMsg = {
            role: "assistant",
            content: `⚠️ ${data.data}`,
            id: Date.now(),
            isError: true,
            sources: [],
          };
          setMessages((prev) => [...prev, errorMsg]);
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
      
      const errorMsg = {
        role: "assistant",
        content: "⚠️ I'm having trouble connecting right now. Please try again in a moment.",
        id: Date.now(),
        isError: true,
        sources: [],
      };
      setMessages((prev) => [...prev, errorMsg]);
    };
  };

  // Export handlers
  const handleExportMarkdown = () => {
    if (messages.length === 0) {
      alert('No messages to export');
      return;
    }
    exportChatAsMarkdown(messages, sessionTitle);
  };
  const handleExportPDF = () => {
    if (messages.length === 0) {
      alert('No messages to export');
      return;
    }
    exportChatAsPDF(messages, sessionTitle);
  };


  return (
    <div style={{ 
      display: "flex", 
      flexDirection: "column", 
      height: "100%", 
      width: "100%"
    }}>
      
      {/* HEADER - Always visible */}
      <div style={{ 
        borderBottom: '1px solid #374151', 
        padding: '12px 24px', 
        display: 'flex', 
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#0F0F0F',
        minHeight: '56px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Sparkles size={18} color="#7C3AED" />
          <h2 style={{ color: 'white', fontSize: '17px', fontWeight: '600', margin: 0 }}>
            {sessionTitle || "New Chat"}
          </h2>
        </div>
        
        {messages.length > 0 && (
          <ExportChatMenu 
            onExportMarkdown={handleExportMarkdown}
            onExportPDF={handleExportPDF}
            currentSessionTitle={sessionTitle}
          />
        )}
      </div>

      {/* MESSAGES AREA - Scrollable */}
      <div 
        ref={messagesContainerRef}
        style={{ 
          flex: 1, 
          overflowY: "auto", 
          background: "#0F0F0F",
          padding: "20px"
        }}
      >
        {messages.length === 0 ? (
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
            <div ref={messagesEndRef} style={{ height: '20px' }} />
          </div>
        )}
      </div>

      {/* INPUT AREA - Always visible */}
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
}
