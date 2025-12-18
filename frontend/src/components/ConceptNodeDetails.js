import React, { useMemo } from 'react';

const ConceptNodeDetails = ({ node, onClose, allNodes, allEdges }) => {
  // Find related concepts (connected nodes)
  const relatedConcepts = useMemo(() => {
    const currentNodeId = allNodes.find(n => n.label === node.label)?.id;
    if (!currentNodeId) return [];

    const related = [];
    
    // Find outgoing connections
    allEdges.forEach(edge => {
      if (edge.from === currentNodeId) {
        const targetNode = allNodes.find(n => n.id === edge.to);
        if (targetNode) {
          related.push({
            label: targetNode.label,
            relationship: edge.label,
            direction: 'outgoing'
          });
        }
      }
      // Find incoming connections
      if (edge.to === currentNodeId) {
        const sourceNode = allNodes.find(n => n.id === edge.from);
        if (sourceNode) {
          related.push({
            label: sourceNode.label,
            relationship: edge.label,
            direction: 'incoming'
          });
        }
      }
    });

    return related;
  }, [node, allNodes, allEdges]);

  // Get source badge color
  const getSourceBadgeStyle = (sourceType) => {
    switch(sourceType) {
      case 'web':
        return { background: '#3b82f6', text: '🌐 Web' };
      case 'document':
        return { background: '#10b981', text: '📄 Document' };
      case 'both':
        return { background: '#8b5cf6', text: '🔗 Mixed' };
      default:
        return { background: '#6b7280', text: '❓ Unknown' };
    }
  };

  const sourceBadge = getSourceBadgeStyle(node.source_type);

  return (
    <div className="node-details-overlay" onClick={onClose}>
      <div className="node-details-popup" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="details-header">
          <div>
            <h3 className="details-title">{node.label}</h3>
            <span 
              className="source-badge-large"
              style={{ background: sourceBadge.background }}
            >
              {sourceBadge.text}
            </span>
          </div>
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>

        {/* Definition */}
        <div className="details-section">
          <h4 className="section-title">📝 Definition</h4>
          <p className="definition-text">{node.definition}</p>
        </div>

        {/* Sources */}
        {node.sources && node.sources.length > 0 && (
          <div className="details-section">
            <h4 className="section-title">🔗 Sources</h4>
            <div className="sources-list">
              {node.sources.map((source, index) => (
                <div key={index} className="source-item">
                  {source.startsWith('http') ? (
                    <a 
                      href={source} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="source-link"
                    >
                      🌐 {source.length > 60 ? source.substring(0, 60) + '...' : source}
                    </a>
                  ) : (
                    <span className="source-doc">
                      📄 {source}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Related Concepts */}
        {relatedConcepts.length > 0 && (
          <div className="details-section">
            <h4 className="section-title">🔗 Related Concepts ({relatedConcepts.length})</h4>
            <div className="related-concepts">
              {relatedConcepts.map((concept, index) => (
                <div key={index} className="related-item">
                  <span className="relationship-arrow">
                    {concept.direction === 'outgoing' ? '→' : '←'}
                  </span>
                  <div className="related-info">
                    <span className="related-label">{concept.label}</span>
                    <span className="relationship-type">{concept.relationship}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConceptNodeDetails;
