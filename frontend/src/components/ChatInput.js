import React, { useState, useRef } from 'react';
import { Send } from 'lucide-react';

export default function ChatInput({ onSend, disabled }) {
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState('quick');
  const textareaRef = useRef(null);

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message, mode);
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e) => {
    setMessage(e.target.value);
    // Auto-resize textarea
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  };

  return (
    <div 
      className="glass border-t border-border/50 px-4 lg:px-6 py-4" 
      style={{ background: "rgba(15, 15, 15, 0.9)" }}
    >
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-3">
          {/* Mode Selector */}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="w-[160px] h-[52px] bg-input border border-border text-foreground rounded-xl px-3 focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all outline-none"
          >
            <option value="quick">Quick</option>
            <option value="detailed">Detailed</option>
            <option value="step-by-step">Step-by-step</option>
          </select>

          {/* Input Field */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={message}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask me anything..."
              disabled={disabled}
              className="w-full min-h-[52px] max-h-[200px] resize-none bg-input border border-border text-foreground px-4 py-3 pr-12 focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all rounded-xl outline-none placeholder:text-muted disabled:opacity-50"
              rows={1}
            />
          </div>

          {/* Send Button */}
          <button
            onClick={handleSend}
            disabled={!message.trim() || disabled}
            className="h-[52px] w-[52px] bg-gradient-to-r from-[#4F46E5] to-[#7C3AED] hover:from-[#4338CA] hover:to-[#6D28D9] text-white rounded-xl transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed flex items-center justify-center"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>

        <p className="text-xs text-muted mt-2 text-center">
          Press Enter to send, Shift + Enter for new line
        </p>
      </div>
    </div>
  );
}
