import React, { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import ConceptNodeDetails from './ConceptNodeDetails';
import ConceptMapControls from './ConceptMapControls';

const ConceptMapViewer = ({ mapData, onBack, onDelete }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [showNodeDetails, setShowNodeDetails] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Initialize graph layout using dagre
  useEffect(() => {
    if (mapData && mapData.nodes && mapData.edges) {
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        mapData.nodes,
        mapData.edges
      );
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    }
  }, [mapData, setNodes, setEdges]);

  // Auto-layout algorithm using dagre
  const getLayoutedElements = (nodes, edges) => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    
    const nodeWidth = 200;
    const nodeHeight = 80;
    
    dagreGraph.setGraph({ 
      rankdir: 'TB', // Top to Bottom
      nodesep: 100,
      ranksep: 150,
      marginx: 50,
      marginy: 50
    });

    // Add nodes to dagre
    nodes.forEach((node) => {
      dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });

    // Add edges to dagre
    edges.forEach((edge) => {
      dagreGraph.setEdge(edge.from, edge.to);
    });

    // Calculate layout
    dagre.layout(dagreGraph);

    // Apply layout to React Flow nodes
    const layoutedNodes = nodes.map((node) => {
      const nodeWithPosition = dagreGraph.node(node.id);
      
      // Determine node color based on source type
      let nodeColor = '#3b82f6'; // blue (default/web)
      let borderColor = '#2563eb';
      
      if (node.source_type === 'document') {
        nodeColor = '#10b981'; // green
        borderColor = '#059669';
      } else if (node.source_type === 'both') {
        nodeColor = '#8b5cf6'; // purple
        borderColor = '#7c3aed';
      }

      return {
        id: node.id,
        data: { 
          label: node.label,
          definition: node.definition,
          sources: node.sources,
          source_type: node.source_type
        },
        position: {
          x: nodeWithPosition.x - nodeWidth / 2,
          y: nodeWithPosition.y - nodeHeight / 2,
        },
        style: {
          background: nodeColor,
          color: 'white',
          border: `2px solid ${borderColor}`,
          borderRadius: '8px',
          padding: '12px',
          fontSize: '13px',
          fontWeight: '500',
          width: nodeWidth,
          cursor: 'pointer',
        },
      };
    });

    // Apply layout to React Flow edges
    const layoutedEdges = edges.map((edge) => ({
      id: `${edge.from}-${edge.to}`,
      source: edge.from,
      target: edge.to,
      label: edge.label,
      type: 'smoothstep',
      animated: true,
      style: { 
        stroke: '#6b7280',
        strokeWidth: 2
      },
      labelStyle: {
        fill: '#9ca3af',
        fontSize: 11,
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: '#1f2937',
        fillOpacity: 0.9,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#6b7280',
      },
    }));

    return { nodes: layoutedNodes, edges: layoutedEdges };
  };

  // Handle node click
  const onNodeClick = useCallback((event, node) => {
    setSelectedNode(node.data);
    setShowNodeDetails(true);
  }, []);

  // Close node details
  const handleCloseDetails = () => {
    setShowNodeDetails(false);
    setSelectedNode(null);
  };

  // Export as image
  const handleExport = () => {
    // This will be implemented in ConceptMapControls
    alert('Export feature coming soon!');
  };

  // ← ADD THIS FUNCTION
  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  // Close fullscreen on Escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isFullscreen]);

  return (
    <div className={`concept-map-viewer ${isFullscreen ? 'fullscreen-mode' : ''}`}>
      {/* Header */}
      <div className="viewer-header">
        <button onClick={onBack} className="back-button">
          ← Back to Maps
        </button>
        
        <div className="viewer-title">
          <h2 className="text-2xl font-bold text-white">{mapData.topic}</h2>
          <p className="text-sm text-gray-400">
            {mapData.nodes.length} concepts • {mapData.edges.length} connections
          </p>
        </div>

        <ConceptMapControls
          onExport={handleExport}
          onDelete={onDelete}
          onToggleFullscreen={toggleFullscreen}
          isFullscreen={isFullscreen}
        />
      </div>

      {/* Legend */}
      <div className="graph-legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ background: '#3b82f6' }}></span>
          Web Sources
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: '#10b981' }}></span>
          Document Sources
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: '#8b5cf6' }}></span>
          Both Sources
        </span>
      </div>

      {/* React Flow Graph */}
      <div className="graph-container">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.2}
          maxZoom={2}
          defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        >
          <Background 
            color="#374151" 
            gap={16} 
            size={1}
            variant="dots"
          />
          <Controls 
            style={{
              background: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
          />
          <MiniMap
            nodeColor={(node) => node.style.background}
            style={{
              background: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
            maskColor="rgba(0, 0, 0, 0.6)"
          />
        </ReactFlow>
      </div>

      {/* Node Details Popup */}
      {showNodeDetails && selectedNode && (
        <ConceptNodeDetails
          node={selectedNode}
          onClose={handleCloseDetails}
          allNodes={mapData.nodes}
          allEdges={mapData.edges}
        />
      )}

      {/* Map Metadata */}
      <div className="map-metadata">
        <div className="metadata-item">
          <span className="metadata-label">Created:</span>
          <span className="metadata-value">
            {new Date(mapData.created_at).toLocaleDateString()}
          </span>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">Sources:</span>
          <span className="metadata-value">
            {mapData.sources.web} web, {mapData.sources.documents} docs
          </span>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">Confidence:</span>
          <span className="metadata-value">
            {mapData.metadata.confidence}%
          </span>
        </div>
      </div>
    </div>
  );
};

export default ConceptMapViewer;
