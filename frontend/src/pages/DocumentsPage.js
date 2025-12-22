import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import DocumentList from "../components/DocumentList";
import DocumentUpload from "../components/DocumentUpload";
import { FileText, Upload, Trash2, AlertCircle } from "lucide-react";
import { API_BASE_URL } from '../config/api';

export default function DocumentsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_BASE_URL}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (!response.ok) {
        throw new Error("Failed to fetch documents");
      }
      
      const data = await response.json();
      setDocuments(data);
    } catch (err) {
      setError(err.message);
      console.error("Error fetching documents:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file) => {
    try {
      setUploading(true);
      setError(null);
      
      const token = localStorage.getItem("token");
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Upload failed");
      }

      await fetchDocuments();
    } catch (err) {
      setError(err.message);
      console.error("Error uploading document:", err);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (documentId) => {
    if (!window.confirm("Delete this document? This will remove it from all sessions.")) {
      return;
    }

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        throw new Error("Failed to delete document");
      }

      await fetchDocuments();
    } catch (err) {
      setError(err.message);
      console.error("Error deleting document:", err);
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: "#0F0F0F" }}>
      {/* Top Navigation */}
      <TopNav 
        user={user} 
        onLogout={handleLogout}
        onToggleSidebar={() => {}} // No sidebar on this page
      />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-8">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent mb-2">
              Document Management
            </h1>
            <p className="text-muted-foreground">
              Upload study materials and manage your document library
            </p>
          </div>

          {/* Error Alert */}
          {error && (
            <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-destructive font-medium">Error</p>
                <p className="text-sm text-destructive/80">{error}</p>
              </div>
            </div>
          )}

          {/* Upload Section */}
          <DocumentUpload onUpload={handleUpload} uploading={uploading} />

          {/* Documents List */}
          <div className="mt-8">
            <h2 className="text-xl font-semibold text-foreground mb-4">
              Your Documents ({documents.length})
            </h2>
            
            {loading ? (
              <div className="text-center py-12">
                <div className="inline-block w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                <p className="text-muted-foreground mt-4">Loading documents...</p>
              </div>
            ) : documents.length === 0 ? (
              <div className="text-center py-12 glass border border-border/50 rounded-2xl">
                <FileText className="w-16 h-16 text-muted-foreground/40 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-foreground mb-2">No documents yet</h3>
                <p className="text-sm text-muted-foreground">Upload your first document to get started</p>
              </div>
            ) : (
              <DocumentList documents={documents} onDelete={handleDelete} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
