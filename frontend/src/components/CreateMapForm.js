import React, { useState } from 'react';
import { Sparkles, AlertCircle, Globe, FileText } from 'lucide-react';
import { API_BASE_URL } from '../config/api';

const CreateMapForm = ({ onMapCreated, onCancel }) => {
  const [topic, setTopic] = useState('');
  const [useWeb, setUseWeb] = useState(true);
  const [useDocuments, setUseDocuments] = useState(false);
  const [maxConcepts, setMaxConcepts] = useState(15);
  const [maxEdges, setMaxEdges] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!topic.trim()) {
      setError('Please enter a topic');
      return;
    }

    if (!useWeb && !useDocuments) {
      setError('Please select at least one source (Web or Documents)');
      return;
    }

    setLoading(true);
    setError(null);
    setProgress('🔍 Retrieving context...');

    try {
      const token = localStorage.getItem('token');
      
      const response = await fetch(`${API_BASE_URL}/api/concepts/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          topic: topic.trim(),
          use_web: useWeb,
          use_documents: useDocuments,
          max_concepts: maxConcepts,
          max_edges: maxEdges
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate concept map');
      }

      setProgress('🧠 Extracting concepts...');
      
      const data = await response.json();
      
      setProgress('✅ Concept map created!');
      
      // Call parent callback
      setTimeout(() => {
        onMapCreated(data);
      }, 500);

    } catch (err) {
      setError(err.message);
      console.error('Error generating map:', err);
    } finally {
      setLoading(false);
      setProgress('');
    }
  };

  return (
    <div className="glass border border-border/50 rounded-2xl p-8">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Topic Input */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            📚 Topic <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Neural Networks, Quantum Computing, Photosynthesis"
            className="w-full px-4 py-3 rounded-lg bg-white/5 border border-border/50 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all"
            disabled={loading}
            maxLength={500}
          />
          <p className="text-xs text-muted-foreground mt-2">
            Enter any topic you want to learn about
          </p>
        </div>

        {/* Source Selection */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            🔍 Sources
          </label>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setUseWeb(!useWeb)}
              disabled={loading}
              className={`
                p-4 rounded-lg border-2 transition-all text-left
                ${useWeb
                  ? 'border-primary bg-primary/10'
                  : 'border-border/30 hover:border-border/50 bg-white/5'
                }
              `}
            >
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={useWeb}
                  onChange={() => {}}
                  disabled={loading}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Globe className="w-5 h-5 text-blue-400" />
                    <span className="font-medium text-foreground">Web Search</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Search online for information
                  </p>
                </div>
              </div>
            </button>

            
          </div>
        </div>

        {/* Advanced Settings */}
        <details className="group">
          <summary className="cursor-pointer list-none">
            <div className="p-4 rounded-lg bg-white/5 border border-border/30 hover:border-border/50 transition-all">
              <span className="text-sm font-medium text-foreground">⚙️ Advanced Settings</span>
            </div>
          </summary>
          
          <div className="mt-4 space-y-4 p-4 rounded-lg bg-white/5 border border-border/30">
            {/* Max Concepts Slider */}
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Max Concepts
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="5"
                  max="30"
                  value={maxConcepts}
                  onChange={(e) => setMaxConcepts(Number(e.target.value))}
                  disabled={loading}
                  className="flex-1"
                />
                <div className="w-12 h-12 flex items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                  <span className="text-lg font-bold text-primary">{maxConcepts}</span>
                </div>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground mt-2">
                <span>5</span>
                <span>30</span>
              </div>
            </div>

            {/* Max Edges Slider */}
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Max Connections
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="5"
                  max="50"
                  value={maxEdges}
                  onChange={(e) => setMaxEdges(Number(e.target.value))}
                  disabled={loading}
                  className="flex-1"
                />
                <div className="w-12 h-12 flex items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                  <span className="text-lg font-bold text-primary">{maxEdges}</span>
                </div>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground mt-2">
                <span>5</span>
                <span>50</span>
              </div>
            </div>
          </div>
        </details>

        {/* Error Display */}
        {error && (
          <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-red-400 font-medium">Error</p>
              <p className="text-sm text-red-400/80">{error}</p>
            </div>
          </div>
        )}

        {/* Progress Display */}
        {loading && progress && (
          <div className="p-4 rounded-lg bg-primary/10 border border-primary/20 flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-primary">{progress}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-6 py-4 rounded-lg bg-white/5 border border-border/50 text-foreground font-medium hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary/20"
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Generating...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                <span>Generate Map</span>
              </>
            )}
          </button>
        </div>

        {/* Info Box */}
        {!loading && (
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              ⏱️ Generation typically takes 15-30 seconds
            </p>
          </div>
        )}
      </form>
    </div>
  );
};

export default CreateMapForm;
