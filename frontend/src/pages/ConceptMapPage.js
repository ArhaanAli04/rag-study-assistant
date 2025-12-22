import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import MapListView from "../components/MapListView";
import CreateMapForm from "../components/CreateMapForm";
import ConceptMapViewer from "../components/ConceptMapViewer";
import { Network, ArrowLeft } from "lucide-react";
import { API_BASE_URL } from '../config/api';

export default function ConceptMapPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [view, setView] = useState('list'); // 'list', 'create', 'viewer'
  const [maps, setMaps] = useState([]);
  const [selectedMap, setSelectedMap] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch all maps on component mount
  useEffect(() => {
    if (view === 'list') {
      fetchMaps();
    }
  }, [view]);

  // Fetch all concept maps from API
  const fetchMaps = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/concepts/maps`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch maps');
      }

      const data = await response.json();
      setMaps(data.maps || []);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching maps:', err);
    } finally {
      setLoading(false);
    }
  };

  // View a specific map
  const handleViewMap = async (mapId) => {
    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/concepts/maps/${mapId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch map details');
      }

      const data = await response.json();
      setSelectedMap(data);
      setView('viewer');
    } catch (err) {
      setError(err.message);
      console.error('Error fetching map:', err);
    } finally {
      setLoading(false);
    }
  };

  // Delete a map
  const handleDeleteMap = async (mapId) => {
    if (!window.confirm('Are you sure you want to delete this concept map?')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/concepts/maps/${mapId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to delete map');
      }

      // Refresh the list
      fetchMaps();
    } catch (err) {
      setError(err.message);
      console.error('Error deleting map:', err);
    }
  };

  // Go back to list view
  const handleBackToList = () => {
    setView('list');
    setSelectedMap(null);
    setError(null);
  };

  // Handle successful map creation
  const handleMapCreated = (newMap) => {
    setView('list');
    fetchMaps(); // Refresh the list
  };

  // Handle logout
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: "#0F0F0F" }}>
      {/* Top Navigation */}
      <TopNav 
        user={user} 
        onLogout={handleLogout}
        onToggleSidebar={() => navigate('/chat')}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            
            
            <div className="flex items-center gap-3 mb-2">
              <Network className="w-8 h-8 text-primary" />
              <h1 className="text-3xl font-bold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent">
                Concept Maps
              </h1>
            </div>
            <p className="text-muted-foreground">
              Generate interactive knowledge graphs from any topic
            </p>
          </div>

          {/* View Toggle */}
          {view !== 'viewer' && (
            <div className="flex gap-3 mb-6">
                <button
                onClick={() => setView('list')}
                className={`
                    flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all
                    ${view === 'list'
                    ? 'bg-primary text-white shadow-lg shadow-primary/20'
                    : 'bg-white/5 text-muted-foreground border border-border/50 hover:border-primary/50 hover:text-foreground'
                    }
                `}
                >
                📚 My Maps
                </button>
                <button
                onClick={() => setView('create')}
                className={`
                    flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all
                    ${view === 'create'
                    ? 'bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white shadow-lg shadow-primary/20'
                    : 'bg-white/5 text-muted-foreground border border-border/50 hover:border-primary/50 hover:text-foreground'
                    }
                `}
                >
                ✨ Create New
                </button>
            </div>
            )}

          {/* Error Display */}
          {error && (
            <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3">
                <span className="text-red-400">⚠️ {error}</span>
                <button 
                onClick={() => setError(null)}
                className="ml-auto text-red-400 hover:text-red-300 transition-all"
                >
                ✕
                </button>
            </div>
            )}

          {/* Main Content */}
          <div>
            {view === 'list' && (
              <MapListView
                maps={maps}
                loading={loading}
                onViewMap={handleViewMap}
                onDeleteMap={handleDeleteMap}
              />
            )}

            {view === 'create' && (
              <CreateMapForm
                onMapCreated={handleMapCreated}
                onCancel={() => setView('list')}
              />
            )}

            {view === 'viewer' && selectedMap && (
              <ConceptMapViewer
                mapData={selectedMap}
                onBack={handleBackToList}
                onDelete={() => handleDeleteMap(selectedMap.id)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
