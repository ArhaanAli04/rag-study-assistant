import React, { useState } from 'react';

const ConceptMapControls = ({ onExport, onDelete, onToggleFullscreen, isFullscreen }) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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

        {/* Export Button */}
        <button
        onClick={onExport}
        className="control-btn"
        title="Export as image"
        >
        📥 Export
        </button>

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
