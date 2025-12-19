import React, { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';

const SessionRenameModal = ({ session, onClose, onRename }) => {
  const [newTitle, setNewTitle] = useState(session.title || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  // Focus input when modal opens
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const trimmedTitle = newTitle.trim();
    
    // Validation
    if (!trimmedTitle) {
      setError('Title cannot be empty');
      return;
    }
    
    if (trimmedTitle.length > 100) {
      setError('Title too long (max 100 characters)');
      return;
    }

    if (trimmedTitle === session.title) {
      onClose();
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      await onRename(session.id, trimmedTitle);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to rename session');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[10000] p-4"
      onClick={onClose}
    >
      <div 
        className="bg-[#1F2937] border border-[#374151] rounded-xl p-6 max-w-md w-full shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">
            Rename Conversation
          </h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/10 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">
              New Title
            </label>
            <input
              ref={inputRef}
              type="text"
              value={newTitle}
              onChange={(e) => {
                setNewTitle(e.target.value);
                setError('');
              }}
              placeholder="Enter conversation title..."
              className="w-full px-4 py-3 bg-[#111827] border border-[#374151] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
              maxLength={100}
              disabled={isSubmitting}
            />
            
            {/* Character count */}
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-gray-500">
                {newTitle.length}/100 characters
              </span>
              {error && (
                <span className="text-xs text-red-400">
                  {error}
                </span>
              )}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 bg-[#374151] text-white rounded-lg font-medium hover:bg-[#4B5563] transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2.5 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting || !newTitle.trim()}
            >
              {isSubmitting ? 'Renaming...' : 'Rename'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default SessionRenameModal;
