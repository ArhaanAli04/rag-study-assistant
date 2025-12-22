import React from 'react';
import { ThumbsUp, ThumbsDown, FileText, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '../lib/utils';
import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config/api';

export default function MessageList({ 
  messages, 
  streamingAnswer,
  onFeedback,
  showCommentFor,
  feedbackComment,
  onCommentChange,
  onCancelComment
}) {
  const [copiedId, setCopiedId] = useState(null);
  const [userProfile, setUserProfile] = useState({ name: '', profilePicture: '' }); // ← ADD THIS

  // ← ADD THIS: Fetch user profile
  useEffect(() => {
    const fetchUserProfile = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE_URL}/user/profile`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setUserProfile({
            name: data.name || '',
            profilePicture: data.profile_picture || ''
          });
        }
      } catch (error) {
        console.error('Failed to fetch user profile:', error);
      }
    };

    fetchUserProfile();
  }, []);

  // ← ADD THIS: Get user initials
  const getUserInitials = () => {
    if (userProfile.name && userProfile.name.trim()) {
      const nameParts = userProfile.name.trim().split(' ');
      
      if (nameParts.length >= 2) {
        return (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase();
      } else {
        return userProfile.name.substring(0, 2).toUpperCase();
      }
    }
    
    return 'US'; // Default fallback
  };

  const handleCopyQuery = (text, messageId) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(messageId);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  return (
    <>
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={cn(
            "animate-fade-in flex gap-3 mb-6",
            msg.role === "user" ? "justify-end" : ""
          )}
        >
          {/* AI Avatar (left side for assistant) */}
          {msg.role === "assistant" && (
            <div className="w-8 h-8 mt-1 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold flex-shrink-0">
              AI
            </div>
          )}

          {/* Message Content */}
          <div className={cn("flex-1 max-w-3xl", msg.role === "user" ? "flex justify-end" : "")}>
            {/* Message Bubble */}
            <div
              className={cn(
                "px-4 py-3 rounded-2xl transition-all hover:shadow-lg",
                msg.role === "user"
                  ? "bg-[#2563EB] text-white ml-auto max-w-2xl"
                  : "bg-[#1F2937] border border-[#374151] text-foreground"
              )}
            >
              {msg.role === "assistant" ? (
                <div className="prose prose-sm max-w-none text-foreground">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                      strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
                      code: ({ children, inline }) => 
                        inline ? (
                          <code className="bg-black/30 px-1.5 py-0.5 rounded text-sm font-mono text-white">{children}</code>
                        ) : (
                          <code className="block bg-black/50 p-3 rounded-lg text-sm font-mono text-white overflow-x-auto my-2">{children}</code>
                        ),
                      ul: ({ children }) => <ul className="list-disc ml-4 mb-2">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal ml-4 mb-2">{children}</ol>,
                      li: ({ children }) => <li className="mb-1">{children}</li>,
                      table: ({ children }) => (
                        <div className="overflow-x-auto my-4">
                          <table className="min-w-full border-collapse border border-[#374151] rounded-lg">
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className="bg-[#374151]/50">{children}</thead>
                      ),
                      th: ({ children }) => (
                        <th className="px-4 py-3 text-left text-sm font-semibold text-white border border-[#374151]">
                          {children}
                        </th>
                      ),
                      tbody: ({ children }) => (
                        <tbody>{children}</tbody>
                      ),
                      tr: ({ children }) => (
                        <tr className="hover:bg-white/5 transition-colors">{children}</tr>
                      ),
                      td: ({ children }) => (
                        <td className="px-4 py-3 text-sm text-foreground/90 border border-[#374151]">
                          {children}
                        </td>
                      ),
                      a: ({ children, href }) => (
                        <a 
                          href={href} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-primary hover:underline break-all"
                        >
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="leading-relaxed">{msg.content}</p>
              )}
            </div>

            {/* Source Citations */}
            {msg.sources && msg.sources.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {msg.sources.map((source, srcIdx) => (
                  <button
                    key={srcIdx}
                    className="glass px-3 py-2 rounded-lg border border-border/50 hover:border-primary/50 hover:scale-105 transition-all group"
                    style={{ background: "rgba(31, 41, 55, 0.6)" }}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <FileText className="w-4 h-4 text-muted group-hover:text-primary transition-colors" />
                      <span className="text-foreground font-medium">
                        {source.file_name || source.url || 'Source'}
                      </span>
                      {source.page_num && (
                        <span className="px-1.5 py-0.5 bg-primary/20 text-primary rounded text-xs">
                          p.{source.page_num}
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Feedback Buttons (only for assistant messages) */}
            {msg.role === 'assistant' && msg.id && (
              <div className="flex items-center gap-2 mt-3">
                <button
                  onClick={() => handleCopyQuery(msg.content, msg.id)}
                  className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 transition-all"
                  title="Copy response"
                >
                  {copiedId === msg.id ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
                <button
                  onClick={() => onFeedback(msg.id, 'up')}
                  disabled={msg.userFeedback}
                  className={cn(
                    "h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 transition-all",
                    msg.userFeedback === 'up' && "text-primary bg-primary/10"
                  )}
                >
                  <ThumbsUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onFeedback(msg.id, 'down')}
                  disabled={msg.userFeedback}
                  className={cn(
                    "h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 transition-all",
                    msg.userFeedback === 'down' && "text-destructive bg-destructive/10"
                  )}
                >
                  <ThumbsDown className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Comment Box */}
            {showCommentFor === msg.id && (
              <div className="mt-3 animate-slide-down">
                <textarea
                  placeholder="What could be improved?"
                  value={feedbackComment}
                  onChange={(e) => onCommentChange(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 bg-input border border-border rounded-lg text-foreground focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all resize-none"
                />
                <div className="flex justify-end gap-2 mt-2">
                  <button
                    onClick={onCancelComment}
                    className="px-3 py-1.5 text-sm rounded-lg hover:bg-white/5 transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => onFeedback(msg.id, 'down')}
                    className="px-3 py-1.5 text-sm bg-primary hover:bg-primary/90 rounded-lg transition-all"
                  >
                    Submit
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ← UPDATED: User Avatar with Profile Picture */}
          {msg.role === "user" && (
            <div className="flex flex-col items-end gap-2">
              <button
                className="w-8 h-8 mt-1 rounded-full bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center text-sm font-semibold text-white hover:scale-105 transition-transform cursor-pointer overflow-hidden flex-shrink-0"
                title={userProfile.name || 'User'}
              >
                {userProfile.profilePicture ? (
                  <img 
                    src={userProfile.profilePicture} 
                    alt="Profile" 
                    className="w-full h-full object-cover"
                    crossOrigin="anonymous"
                    referrerPolicy="no-referrer"
                    onError={(e) => {
                      console.error('Image load failed:', userProfile.profilePicture);
                      e.target.style.display = 'none';
                      e.target.parentElement.innerText = getUserInitials();
                    }}
                    onLoad={() => console.log('Profile image loaded successfully')}
                  />
                ) : (
                  getUserInitials()
                )}
              </button>
              
              {/* Copy Button */}
              <button
                onClick={() => handleCopyQuery(msg.content, msg.id)}
                className="flex items-center gap-1.5 px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 rounded-lg transition-all"
                title="Copy query"
              >
                {copiedId === msg.id ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-green-400" />
                    <span></span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span></span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      ))}

      {/* Streaming Answer */}
      {streamingAnswer && (
        <div className="animate-fade-in flex gap-3 mb-6">
          <div className="w-8 h-8 mt-1 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold flex-shrink-0">
            AI
          </div>
          <div className="flex-1 max-w-3xl">
            <div className="px-4 py-3 rounded-2xl bg-[#1F2937] border border-[#374151] text-foreground">
              <p className="leading-relaxed">{streamingAnswer}</p>
              <span className="inline-block w-2 h-4 bg-primary ml-1 animate-pulse">▊</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
