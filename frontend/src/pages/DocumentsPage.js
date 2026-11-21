import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import DocumentList from "../components/DocumentList";
import DocumentUpload from "../components/DocumentUpload";
import { FileText, AlertCircle, CheckCircle2, FolderKanban } from "lucide-react";
import { API_BASE_URL } from '../config/api';
import { deleteNotice, uploadNotice } from "../utils/uploadNotice";
import { activeProjects, listProjects, moveDocument } from "../services/projectsApi";
import { deleteDocument, uploadDocument } from "../services/documentsApi";

// The document filter: every document, the unassigned ones, or one project's (by id, as a string).
const ALL = "all";
const NO_PROJECT = "none";

function matchesFilter(doc, filter) {
  if (filter === ALL) return true;
  if (filter === NO_PROJECT) return doc.project_id === null || doc.project_id === undefined;
  return String(doc.project_id) === filter;
}

export default function DocumentsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Day 18: projects, the upload's target project and the list filter.
  const [projects, setProjects] = useState([]);
  const [projectsError, setProjectsError] = useState(null);
  const [uploadProjectId, setUploadProjectId] = useState("");
  const [filter, setFilter] = useState(ALL);
  const [movingId, setMovingId] = useState(null);

  const fetchDocuments = useCallback(async () => {
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
  }, []);

  const fetchProjects = useCallback(async () => {
    setProjectsError(null);
    try {
      const data = await listProjects();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setProjectsError(err.message);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    fetchProjects();
  }, [fetchDocuments, fetchProjects]);

  // After any project change: refresh both lists (counts, badges) and say what happened.
  const handleProjectsChanged = async (message) => {
    setError(null);
    setNotice(message);
    await Promise.all([fetchProjects(), fetchDocuments()]);
  };

  const handleUpload = async (file) => {
    try {
      setUploading(true);
      setError(null);
      setNotice(null);
      setNotice(uploadNotice(await uploadDocument(file, uploadProjectId)));
      await Promise.all([fetchDocuments(), fetchProjects()]);
    } catch (err) {
      setError(err.message);
      console.error("Error uploading document:", err);
    } finally {
      setUploading(false);
    }
  };

  const handleMove = async (documentId, projectId) => {
    const doc = documents.find((d) => d.id === documentId);
    const target = projectId === null ? "No project" : projects.find((p) => p.id === projectId)?.name;
    setMovingId(documentId);
    setError(null);
    setNotice(null);
    try {
      await moveDocument(documentId, projectId);
      await handleProjectsChanged(`Moved ${doc?.filename || "the file"} to ${target}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setMovingId(null);
    }
  };

  const handleDelete = async (documentId) => {
    if (!window.confirm("Delete this document and all its versions? New answers won't cite it.")) {
      return;
    }

    const fileName = documents.find((d) => d.id === documentId)?.filename;
    setError(null);
    setNotice(null);
    try {
      const result = await deleteDocument(documentId);
      setNotice(deleteNotice(fileName, result.versions_deleted));
      await Promise.all([fetchDocuments(), fetchProjects()]);
    } catch (err) {
      setError(err.message);
      console.error("Error deleting document:", err);
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const pickable = activeProjects(projects);
  const shown = documents.filter((doc) => matchesFilter(doc, filter));

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
          {notice && (
            <div role="status" className="mb-6 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-emerald-300">{notice}</p>
            </div>
          )}

          {error && (
            <div role="alert" className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-destructive font-medium">Error</p>
                <p className="text-sm text-destructive/80">{error}</p>
              </div>
            </div>
          )}

          {/* Day 19: projects are managed on their own pages; here files go into them. */}
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            {projectsError ? (
              <span role="alert" className="text-amber-400">
                Couldn't load your projects ({projectsError}). Uploads still work without a project.
              </span>
            ) : (
              <span>Upload a file into a project so only that project's chats cite it.</span>
            )}
            <Link
              to="/projects"
              className="inline-flex items-center gap-1 text-primary hover:underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <FolderKanban className="w-4 h-4" aria-hidden="true" /> Manage projects →
            </Link>
          </div>

          {/* Upload Section */}
          <DocumentUpload
            onUpload={handleUpload}
            uploading={uploading}
            projects={pickable}
            projectId={uploadProjectId}
            onProjectChange={setUploadProjectId}
          />

          {/* Documents List */}
          <div className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-foreground">
                Your Documents ({shown.length})
              </h2>
              <div className="flex items-center gap-2">
                <label htmlFor="document-filter" className="text-sm text-muted-foreground">Show</label>
                <select
                  id="document-filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="px-3 py-1.5 bg-white/5 border border-border/50 rounded-lg text-sm text-foreground"
                >
                  <option value={ALL}>All documents</option>
                  <option value={NO_PROJECT}>No project</option>
                  {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
                </select>
              </div>
            </div>

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
            ) : shown.length === 0 ? (
              <div className="text-center py-12 glass border border-border/50 rounded-2xl">
                <p className="text-sm text-muted-foreground">
                  {filter === NO_PROJECT ? "Every document is in a project." : "No documents in this project yet."}
                </p>
              </div>
            ) : (
              <DocumentList
                documents={shown}
                onDelete={handleDelete}
                projects={pickable}
                onMove={handleMove}
                movingId={movingId}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
