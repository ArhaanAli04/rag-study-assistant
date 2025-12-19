import React, { useState, useRef, useEffect } from 'react';

const ConceptMapControls = ({ 
  onExportPNG, 
  onExportJPEG, 
  onDelete, 
  onToggleFullscreen, 
  isFullscreen,
  isExporting 
}) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef(null);

  // Close export menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(event.target)) {
        setShowExportMenu(false);
      }
    };

    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showExportMenu]);

  const handleDeleteClick = () => {
    setShowDeleteConfirm(true);
  };

  const handleConfirmDelete = () => {
    setShowDeleteConfirm(false);
    onDelete();
  };

  const handleCancelDelete = () => {
    setShowDeleteConfirm(false);
  };

  const handleExport = (format) => {
    setShowExportMenu(false);
    if (format === 'png') {
      onExportPNG();
    } else if (format === 'jpeg') {
      onExportJPEG();
    }
  };

  return (
    <div className="map-controls">
      
      {/* Fullscreen Toggle Button */}
      <button
        onClick={onToggleFullscreen}
        className="control-btn"
        title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
      >
        {isFullscreen ? '🔲 Exit' : '⛶ Fullscreen'}
      </button>

      {/* Export Button with Dropdown */}
      <div className="export-dropdown-container" ref={exportMenuRef}>
        <button
          onClick={() => setShowExportMenu(!showExportMenu)}
          className="control-btn"
          title="Export as image"
          disabled={isExporting}
        >
          {isExporting ? '⏳ Exporting...' : '📥 Export'}
        </button>

        {/* Export Dropdown Menu */}
        {showExportMenu && !isExporting && (
          <div className="export-dropdown-menu">
            <div className="export-menu-header">
              Export as Image
            </div>
            
            <button
              onClick={() => handleExport('png')}
              className="export-menu-item"
            >
              <span className="export-icon">🖼️</span>
              <div className="export-info">
                <div className="export-format">PNG Image</div>
                <div className="export-desc">High quality, lossless</div>
              </div>
            </button>

            <button
              onClick={() => handleExport('jpeg')}
              className="export-menu-item"
            >
              <span className="export-icon">📷</span>
              <div className="export-info">
                <div className="export-format">JPEG Image</div>
                <div className="export-desc">Smaller file size</div>
              </div>
            </button>
          </div>
        )}
      </div>

      {/* Delete Button */}
      <button
        onClick={handleDeleteClick}
        className="control-btn delete-btn"
        title="Delete this map"
      >
        🗑️ Delete
      </button>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="delete-confirm-overlay" onClick={handleCancelDelete}>
          <div className="delete-confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-header">
              <span className="confirm-icon">⚠️</span>
              <h3 className="confirm-title">Delete Concept Map?</h3>
            </div>
            
            <p className="confirm-message">
              This action cannot be undone. All nodes and relationships will be permanently deleted.
            </p>

            <div className="confirm-actions">
              <button
                onClick={handleCancelDelete}
                className="btn-cancel-delete"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="btn-confirm-delete"
              >
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ConceptMapControls;
