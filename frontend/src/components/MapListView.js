import React, { useState,useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
const MapListView = ({ maps, loading, onViewMap, onDeleteMap }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('newest'); // 'newest', 'oldest'
  // Inside MapListView component
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [fullscreenMapId, setFullscreenMapId] = useState(null);
  const dropdownRef = useRef(null);
  // Close dropdown when clicking outside
    useEffect(() => {
    const handleClickOutside = (event) => {
        if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowSortDropdown(false);
        }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);
  // Filter maps by search term
  const filteredMaps = maps.filter(map =>
    map.topic.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Sort maps
  const sortedMaps = [...filteredMaps].sort((a, b) => {
    const dateA = new Date(a.created_at);
    const dateB = new Date(b.created_at);
    return sortBy === 'newest' ? dateB - dateA : dateA - dateB;
  });

  // Format date - Treat naive datetime as UTC
    const formatDate = (dateString) => {
    // Backend sends naive datetime (no timezone)
    // We need to treat it as UTC, then convert to IST
    
    // Add 'Z' to indicate UTC if no timezone info exists
    const utcString = dateString.includes('Z') || dateString.includes('+') || dateString.includes('-', 10)
        ? dateString 
        : dateString + 'Z';  // Treat as UTC
    
    const date = new Date(utcString);
    
    return date.toLocaleString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
        timeZone: 'Asia/Kolkata'
    });
    };




  if (loading) {
    return (
      <div className="glass border border-border/50 rounded-2xl p-8">
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-12 h-12 border-4 border-border border-t-primary rounded-full animate-spin mb-4"></div>
          <p className="text-muted-foreground">Loading your concept maps...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Search & Sort Controls */}
      <div className="glass border border-border/50 rounded-2xl p-4 relative z-30">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder="🔍 Search maps by topic..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-border/50 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all"
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-muted-foreground whitespace-nowrap">Sort by:</label>
            
            <div className="relative z-40" ref={dropdownRef}>
                <button
                onClick={() => setShowSortDropdown(!showSortDropdown)}
                className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-white/5 border border-border/50 text-foreground hover:border-border transition-all min-w-[160px]"
                >
                <span>{sortBy === 'newest' ? 'Newest First' : 'Oldest First'}</span>
                <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${showSortDropdown ? 'rotate-180' : ''}`} />
                </button>

                {showSortDropdown && (
                <div className="absolute top-full mt-2 right-0 w-full bg-[#1f2937] border border-border/50 rounded-lg shadow-xl z-[100] overflow-hidden">
                    <button
                    onClick={() => {
                        setSortBy('newest');
                        setShowSortDropdown(false);
                    }}
                    className={`w-full px-4 py-3 text-left transition-all ${
                        sortBy === 'newest' 
                        ? 'bg-primary/10 text-primary' 
                        : 'text-foreground hover:bg-white/5'
                    }`}
                    >
                    Newest First
                    </button>
                    <button
                    onClick={() => {
                        setSortBy('oldest');
                        setShowSortDropdown(false);
                    }}
                    className={`w-full px-4 py-3 text-left transition-all ${
                        sortBy === 'oldest' 
                        ? 'bg-primary/10 text-primary' 
                        : 'text-foreground hover:bg-white/5'
                    }`}
                    >
                    Oldest First
                    </button>
                </div>
                )}
            </div>
            </div>
        </div>
      </div>

      {/* Maps Grid */}
      {sortedMaps.length === 0 ? (
        <div className="glass border border-border/50 rounded-2xl p-12 text-center">
          <div className="text-6xl mb-4">📭</div>
          <h3 className="text-xl font-semibold text-foreground mb-2">
            {searchTerm ? 'No maps found' : 'No concept maps yet'}
          </h3>
          <p className="text-muted-foreground">
            {searchTerm
              ? 'Try a different search term'
              : 'Create your first concept map to get started!'}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedMaps.map((map) => (
              <div key={map.id} className="glass border border-border/50 rounded-2xl p-6 hover:border-primary/50 transition-all">
                {/* Card Header */}
                <div className="flex items-start justify-between mb-4">
                  <h3 className="text-lg font-semibold text-foreground flex-1 pr-2">
                    {map.topic}
                  </h3>
                  <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-500 text-xs font-medium whitespace-nowrap">
                    {map.confidence}% confident
                  </span>
                </div>

                {/* Card Stats */}
                <div className="flex gap-4 mb-4">
                  <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    <span className="text-primary">🔵</span>
                    <span>{map.node_count} concepts</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    <span className="text-primary">🔗</span>
                    <span>{map.edge_count} connections</span>
                  </div>
                </div>

                {/* Sources Info */}
                <div className="flex gap-2 flex-wrap mb-4">
                  {map.sources.web > 0 && (
                    <span className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-xs font-medium">
                      🌐 {map.sources.web} web
                    </span>
                  )}
                  {map.sources.documents > 0 && (
                    <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-xs font-medium">
                      📄 {map.sources.documents} docs
                    </span>
                  )}
                </div>

                {/* Card Footer */}
                <div className="flex items-center justify-between pt-4 border-t border-border/30">
                  <span className="text-sm text-muted-foreground">
                    {formatDate(map.created_at)}
                  </span>

                  <div className="flex gap-2">
                    <button
                      onClick={() => onViewMap(map.id)}
                      className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:opacity-90 transition-all"
                    >
                      👁️ View
                    </button>
                    <button
                      onClick={() => onDeleteMap(map.id)}
                      className="px-3 py-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-all"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Stats Summary */}
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              Showing {sortedMaps.length} of {maps.length} concept maps
            </p>
          </div>
        </>
      )}
    </div>
  );
};

export default MapListView;
