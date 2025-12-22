import { Plus, MessageSquare, Trash2,Edit2 } from 'lucide-react';
import { useState } from 'react'; 
import SessionRenameModal from './SessionRenameModal';
import { API_BASE_URL } from '../config/api';

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}) {
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [sessionToRename, setSessionToRename] = useState(null);
  // Helper to check if two dates are the same day
  const isSameDay = (d1, d2) => {
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate();
  };

  // Enhanced time formatting
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    // Today
    if (isSameDay(date, now)) {
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      return `${diffHours} hours ago`;
    }
    
    // Yesterday
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (isSameDay(date, yesterday)) {
      return `Yesterday at ${date.toLocaleTimeString('en-US', { 
        hour: 'numeric', 
        minute: '2-digit',
        hour12: true 
      })}`;
    }
    
    // This week (2-6 days ago)
    if (diffDays >= 2 && diffDays < 7) {
      return `${diffDays} days ago`;
    }
    
    // Older than a week
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Group sessions by time period
  const groupSessions = () => {
    const now = new Date();
    const groups = {
      today: [],
      yesterday: [],
      thisWeek: [],
      older: []
    };

    sessions.forEach(session => {
      const timeToUse = session.last_message_time || session.created_at;
      const date = new Date(timeToUse);
      const diffMs = now - date;
      const diffDays = Math.floor(diffMs / 86400000);

      // Today
      if (isSameDay(date, now)) {
        groups.today.push(session);
      }
      // Yesterday
      else {
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (isSameDay(date, yesterday)) {
          groups.yesterday.push(session);
        }
        // This week (2-6 days ago)
        else if (diffDays >= 2 && diffDays < 7) {
          groups.thisWeek.push(session);
        }
        // Older (7+ days ago)
        else {
          groups.older.push(session);
        }
      }
    });

    return groups;
  };

  const handleDelete = (e, session) => {
    e.stopPropagation();
    const confirmMessage = session.title 
      ? `Delete "${session.title}"?` 
      : `Delete Session ${session.id}?`;
    if (window.confirm(confirmMessage)) {
      onDeleteSession(session.id);
    }
  };

  const grouped = groupSessions();

  const getTopicColor = (topic) => {
  const colors = {
    "Machine Learning": "bg-blue-500/10 text-blue-400 border-blue-500/30",
    "Deep Learning": "bg-purple-500/10 text-purple-400 border-purple-500/30",
    "Natural Language Processing": "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
    "Computer Vision": "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
    "Python Programming": "bg-green-500/10 text-green-400 border-green-500/30",
    "Data Structures": "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
    "Algorithms": "bg-orange-500/10 text-orange-400 border-orange-500/30",
    "Web Development": "bg-pink-500/10 text-pink-400 border-pink-500/30",
    "Database": "bg-red-500/10 text-red-400 border-red-500/30",
    "System Design": "bg-violet-500/10 text-violet-400 border-violet-500/30",
    "General": "bg-gray-500/10 text-gray-400 border-gray-500/30",
  };
  
  // Find matching color or use default
  for (const [key, value] of Object.entries(colors)) {
    if (topic?.includes(key)) return value;
  }
  return colors["General"];
};
  const handleRenameClick = (e, session) => {
    e.stopPropagation();
    setSessionToRename(session);
    setRenameModalOpen(true);
  };

  const handleRename = async (sessionId, newTitle) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/rename`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ new_title: newTitle }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to rename session');
      }

      // Refresh sessions list (you'll need to call this from parent)
      // For now, just close modal - we'll add proper refresh in next step
      window.location.reload(); // Temporary solution
    } catch (error) {
      console.error('Rename failed:', error);
      throw error;
    }
  };

  const renderSession = (session) => (
    <div
      key={session.id}
      onClick={() => onSelectSession(session.id)}
      className={`
        group relative flex items-start gap-3 p-3 mb-2 rounded-lg cursor-pointer
        transition-all duration-200
        ${activeSessionId === session.id 
          ? 'bg-white/10 border border-border/50' 
          : 'hover:bg-white/5 border border-transparent'
        }
      `}
    >
      <MessageSquare className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
        activeSessionId === session.id ? 'text-primary' : 'text-muted-foreground'
      }`} />
      
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-medium truncate ${
          activeSessionId === session.id ? 'text-foreground' : 'text-foreground/80'
        }`}>
          {session.title || `Session ${session.id}`}
        </div>

        {/* ✅ ADD TOPIC TAG HERE */}
        {session.topic && session.topic !== "General" && (
          <div className="mt-1.5">
            <span className={`inline-flex items-center text-xs px-2 py-0.5 rounded-md border ${getTopicColor(session.topic)}`}>
              {session.topic}
            </span>
          </div>
        )}

        <div className="text-xs text-muted-foreground mt-1">
          {formatDate(session.last_message_time || session.created_at)}
        </div>
      </div>

      {/* ← ADD THIS DIV FOR BUTTONS */}
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => handleRenameClick(e, session)}
          className="p-1 hover:bg-primary/20 rounded transition-all"
          title="Rename conversation"
        >
          <Edit2 className="w-4 h-4 text-primary" />
        </button>
        <button
          onClick={(e) => handleDelete(e, session)}
          className="p-1 hover:bg-destructive/20 rounded transition-all"
          title="Delete conversation"
        >
          <Trash2 className="w-4 h-4 text-destructive" />
        </button>
      </div>
    </div>
  );

  return (
    <aside
      className="glass border-r border-border/50 flex flex-col"
      style={{ 
        width: "280px", 
        background: "rgba(15, 15, 15, 0.8)",
        height: "100vh"
      }}
    >
      {/* New Chat Button */}
      <div className="p-4 border-b border-border/50">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all shadow-lg shadow-primary/20"
        >
          <Plus className="w-5 h-5" />
          New Chat
        </button>
      </div>

      {/* Session List with Grouping */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <MessageSquare className="w-12 h-12 text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">No conversations yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Start a new chat to begin</p>
          </div>
        ) : (
          <>
            {/* Today Section */}
            {grouped.today.length > 0 && (
              <div className="mb-4">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-2">
                  Today
                </h3>
                {grouped.today.map(renderSession)}
              </div>
            )}

            {/* Yesterday Section */}
            {grouped.yesterday.length > 0 && (
              <div className="mb-4">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-2">
                  Yesterday
                </h3>
                {grouped.yesterday.map(renderSession)}
              </div>
            )}

            {/* This Week Section */}
            {grouped.thisWeek.length > 0 && (
              <div className="mb-4">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-2">
                  Previous 7 Days
                </h3>
                {grouped.thisWeek.map(renderSession)}
              </div>
            )}

            {/* Older Section */}
            {grouped.older.length > 0 && (
              <div className="mb-4">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-2 mb-2">
                  Older
                </h3>
                {grouped.older.map(renderSession)}
              </div>
            )}
          </>
        )}
      </div>
      {/* ← ADD RENAME MODAL */}
      {renameModalOpen && sessionToRename && (
        <SessionRenameModal
          session={sessionToRename}
          onClose={() => {
            setRenameModalOpen(false);
            setSessionToRename(null);
          }}
          onRename={handleRename}
        />
      )}
    </aside>
  );
}
