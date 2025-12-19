import React, { useState, useRef, useEffect } from 'react';
import { Download, FileText, FileDown } from 'lucide-react';

const ExportChatMenu = ({ onExportMarkdown, onExportPDF, currentSessionTitle }) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleExport = (format) => {
    if (format === 'markdown') {
      onExportMarkdown();
    } else if (format === 'pdf') {
      onExportPDF();
    }
    setIsOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      {/* Export Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`p-2 rounded-lg transition-all ${
          isOpen ? 'bg-white/10' : 'hover:bg-white/5'
        }`}
        title="Export chat"
      >
        <Download className="w-5 h-5 text-foreground" />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-[#1F2937] border border-[#374151] rounded-lg shadow-xl z-[9999] py-2 animate-fade-in">
          <div className="px-3 py-2 border-b border-[#374151]">
            <p className="text-xs text-gray-400">Export current chat</p>
          </div>

          {/* Markdown Export */}
          <button
            onClick={() => handleExport('markdown')}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-gray-300 hover:bg-white/5 transition-colors"
          >
            <FileText className="w-4 h-4 text-blue-400" />
            <div>
              <div className="font-medium">Markdown (.md)</div>
              <div className="text-xs text-gray-500">Plain text format</div>
            </div>
          </button>

          {/* PDF Export */}
          <button
            onClick={() => handleExport('pdf')}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-gray-300 hover:bg-white/5 transition-colors"
          >
            <FileDown className="w-4 h-4 text-red-400" />
            <div>
              <div className="font-medium">PDF Document</div>
              <div className="text-xs text-gray-500">Formatted document</div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
};

export default ExportChatMenu;
