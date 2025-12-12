import { Plus, MessageSquare, Trash2 } from 'lucide-react';

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
}) {
  
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

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

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <MessageSquare className="w-12 h-12 text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">No conversations yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Start a new chat to begin</p>
          </div>
        ) : (
          sessions.map((session) => (
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
                <div className="text-xs text-muted-foreground mt-1">
                  {formatDate(session.created_at)}
                </div>
              </div>

              {/* Delete Button - shows on hover */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  // TODO: Add delete functionality
                  console.log('Delete session:', session.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/20 rounded transition-all"
              >
                <Trash2 className="w-4 h-4 text-destructive" />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
