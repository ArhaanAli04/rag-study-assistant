// /projects/:projectId (Day 19): one project's files, instructions and chats.
// The id comes from the URL, so it is untrusted: a non-numeric id never reaches the server, and a
// 404 (missing, or another user's project: the server answers both the same) is "Project not found".
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle, AlertTriangle, Archive, ArchiveRestore, ArrowLeft, CheckCircle2, FileText, Folder,
  FolderOutput, FolderX, Loader2, MessageSquare, MessageSquarePlus, Pencil, Trash2,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import DocumentUpload from "../components/DocumentUpload";
import { buttonClass, DeleteDialog, DescriptionEditor, focusRing, InstructionsEditor, RenameForm } from "../components/ProjectEditors";
import {
  deleteProject, getProject, lastActivityText, moveDocument, projectCounts, projectDeletedNotice, updateProject,
} from "../services/projectsApi";
import { deleteDocument, uploadDocument } from "../services/documentsApi";
import { deleteNotice, uploadNotice } from "../utils/uploadNotice";
import { formatRelativeTime, formatShortDate, parseServerTime } from "../utils/serverTime";

const cardClass = "glass border border-border/50 rounded-2xl p-6";
const primaryButton =
  `inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg text-sm font-medium hover:opacity-90 transition-all ${focusRing}`;

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const validId = /^\d+$/.test(projectId || "");

  // loading | ready | notfound | error
  const [state, setState] = useState({ status: validId ? "loading" : "notfound", detail: null, error: null });
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const latestRequest = useRef(0);

  // Each load is numbered; a reply to an older one (the user moved to another project meanwhile) is dropped.
  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!validId) {
      setState({ status: "notfound", detail: null, error: null });
      return;
    }
    const request = ++latestRequest.current;
    if (!quiet) setState({ status: "loading", detail: null, error: null });
    try {
      const detail = await getProject(projectId);
      if (request === latestRequest.current) setState({ status: "ready", detail, error: null });
    } catch (err) {
      if (request !== latestRequest.current) return;
      setState(err.status === 404
        ? { status: "notfound", detail: null, error: null }
        : { status: "error", detail: null, error: err.message });
    }
  }, [projectId, validId]);

  useEffect(() => {
    setNotice(null);
    setError(null);
    load();
  }, [load]);

  // After a change: say what happened and reload quietly, so counts stay the server's.
  const changed = async (message) => {
    setError(null);
    setNotice(message);
    await load({ quiet: true });
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: "#0F0F0F" }}>
      <TopNav user={user} onLogout={handleLogout} onToggleSidebar={() => {}} />
      <main className="flex-1 overflow-y-auto px-4 lg:px-8 py-8">
        <div className="max-w-6xl mx-auto">
          <Link to="/projects" className={`inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6 rounded ${focusRing}`}>
            <ArrowLeft className="w-4 h-4" aria-hidden="true" /> All projects
          </Link>

          {state.status === "loading" && (
            <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" /> Loading project…
            </div>
          )}
          {state.status === "notfound" && (
            <div className={`${cardClass} text-center py-12`}>
              <FolderX className="w-16 h-16 text-muted-foreground/40 mx-auto mb-4" aria-hidden="true" />
              <h1 className="text-lg font-medium text-foreground mb-2">Project not found</h1>
              <p className="text-sm text-muted-foreground mb-4">It may have been deleted, or the link is wrong.</p>
              <Link to="/projects" className={primaryButton}>Back to your projects</Link>
            </div>
          )}
          {state.status === "error" && (
            <div role="alert" className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex flex-wrap items-center gap-3">
              <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0" aria-hidden="true" />
              <span className="text-sm text-destructive">Couldn't load this project: {state.error}</span>
              <button type="button" onClick={() => load()} className={`text-sm text-destructive underline rounded ${focusRing}`}>Try again</button>
            </div>
          )}
          {state.status === "ready" && (
            <ProjectView
              key={state.detail.id}
              project={state.detail}
              notice={notice}
              error={error}
              onError={(message) => { setNotice(null); setError(message); }}
              onChanged={changed}
              onDeleted={(message) => navigate("/projects", { state: { notice: message } })}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function ProjectView({ project, notice, error, onError, onChanged, onDeleted }) {
  const [open, setOpen] = useState(null); // null | "rename" | "delete"
  const [busy, setBusy] = useState(false);
  const [headerError, setHeaderError] = useState(null);

  const run = async (action) => {
    setBusy(true);
    setHeaderError(null);
    try {
      await action();
    } catch (err) {
      setHeaderError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleArchive = () => run(async () => {
    await updateProject(project.id, { archived: !project.archived });
    await onChanged(project.archived ? `Unarchived ${project.name}.` : `Archived ${project.name}: it takes no new files or chats.`);
  });

  return (
    <>
      {notice && (
        <div role="status" className="mb-6 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-emerald-300">{notice}</p>
        </div>
      )}
      {error && (
        <div role="alert" className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <header className={`${cardClass} mb-6`}>
        <div className="flex flex-wrap items-start gap-4">
          <Folder className={`w-8 h-8 flex-shrink-0 ${project.archived ? "text-muted-foreground" : "text-primary"}`} aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-foreground break-words">{project.name}</h1>
              {project.archived && (
                <span className="text-xs px-2 py-0.5 rounded-md border border-amber-500/30 text-amber-400">Archived</span>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1">{projectCounts(project)} · {lastActivityText(project)}</p>
            {project.description && <p className="text-sm text-foreground/80 mt-3 break-words">{project.description}</p>}
          </div>
          {project.archived ? (
            <button type="button" disabled className={`${primaryButton} opacity-50 cursor-not-allowed`}
              title="Unarchive the project to start chats in it">
              <MessageSquarePlus className="w-4 h-4" aria-hidden="true" /> New chat in this project
            </button>
          ) : (
            <Link to={`/chat?project=${project.id}`} className={primaryButton}>
              <MessageSquarePlus className="w-4 h-4" aria-hidden="true" /> New chat in this project
            </Link>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-1 mt-4">
          <button type="button" className={buttonClass} disabled={busy} onClick={() => setOpen(open === "rename" ? null : "rename")}>
            <Pencil className="w-3 h-3" aria-hidden="true" /> Rename
          </button>
          <button type="button" className={buttonClass} disabled={busy} onClick={toggleArchive}>
            {project.archived
              ? <><ArchiveRestore className="w-3 h-3" aria-hidden="true" /> Unarchive</>
              : <><Archive className="w-3 h-3" aria-hidden="true" /> Archive</>}
          </button>
          <button type="button" className={`${buttonClass} text-destructive hover:bg-destructive/10`} disabled={busy}
            onClick={() => setOpen(open === "delete" ? null : "delete")}>
            <Trash2 className="w-3 h-3" aria-hidden="true" /> Delete
          </button>
        </div>
        {headerError && <p role="alert" className="mt-3 text-sm text-destructive">{headerError}</p>}
        {open === "rename" && (
          <RenameForm project={project} busy={busy} onCancel={() => setOpen(null)}
            onSave={(name) => run(async () => {
              await updateProject(project.id, { name });
              setOpen(null);
              await onChanged(`Renamed to ${name}.`);
            })} />
        )}
        {open === "delete" && (
          <DeleteDialog project={project} busy={busy} onCancel={() => setOpen(null)}
            onConfirm={(documents) => run(async () => {
              const result = await deleteProject(project.id, documents);
              onDeleted(projectDeletedNotice(project.name, result));
            })} />
        )}
      </header>

      {project.archived && (
        <div className="mb-6 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20 flex flex-wrap items-center gap-3">
          <Archive className="w-5 h-5 text-amber-400 flex-shrink-0" aria-hidden="true" />
          <p className="text-sm text-amber-300 flex-1">
            This project is archived: it takes no new files or chats. Its chats still open and answer.
          </p>
          <button type="button" className={buttonClass} disabled={busy} onClick={toggleArchive}>Unarchive</button>
        </div>
      )}

      <FilesSection project={project} onChanged={onChanged} onError={onError} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <section aria-labelledby="instructions-heading" className={cardClass}>
          <h2 id="instructions-heading" className="text-lg font-semibold text-foreground mb-1">Instructions</h2>
          <InstructionsEditor project={project} rows={6}
            onSaved={() => onChanged(`Saved the instructions of ${project.name}.`)} />
          <div className="mt-6 pt-4 border-t border-border/50">
            <DescriptionEditor project={project} onSaved={() => onChanged(`Saved the description of ${project.name}.`)} />
          </div>
        </section>
        <ChatsSection project={project} />
      </div>
    </>
  );
}

function FilesSection({ project, onChanged, onError }) {
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  // Thrown errors stay in the upload box (DocumentUpload shows them next to the file).
  const handleUpload = async (file) => {
    setUploading(true);
    try {
      await onChanged(uploadNotice(await uploadDocument(file, project.id)));
    } finally {
      setUploading(false);
    }
  };

  const runOn = async (doc, action) => {
    setBusyId(doc.id);
    try {
      await action();
    } catch (err) {
      onError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const moveOut = (doc) => runOn(doc, async () => {
    await moveDocument(doc.id, null);
    await onChanged(`Moved ${doc.filename} to No project: general chats can cite it now, ${project.name}'s can't.`);
  });

  const remove = (doc) => {
    if (!window.confirm(`Delete ${doc.filename} and all its versions? New answers won't cite it.`)) return;
    runOn(doc, async () => {
      const result = await deleteDocument(doc.id);
      await onChanged(deleteNotice(doc.filename, result.versions_deleted));
    });
  };

  return (
    <section aria-labelledby="files-heading" className={cardClass}>
      <h2 id="files-heading" className="text-lg font-semibold text-foreground mb-1">Files ({project.documents.length})</h2>
      <p className="text-sm text-muted-foreground mb-4">Chats in {project.name} answer only from these files.</p>

      {project.documents.length === 0 ? (
        <div className="text-center py-8 mb-4 border border-dashed border-border/50 rounded-xl">
          <FileText className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            No files yet. {project.archived ? "Unarchive the project to add some." : "Upload this course's slides and notes."}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border/50 mb-4">
          {project.documents.map((doc) => {
            const uploaded = parseServerTime(doc.created_at);
            return (
              <li key={doc.id} aria-label={`File ${doc.filename}`} className="flex flex-wrap items-center gap-3 py-3">
                <FileText className="w-5 h-5 text-primary flex-shrink-0" aria-hidden="true" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{doc.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    Version {doc.version}{uploaded ? ` · uploaded ${formatShortDate(uploaded)}` : ""}
                  </p>
                  {doc.chunks === 0 && (
                    <p className="flex items-center gap-1 text-xs text-amber-400 mt-1">
                      <AlertTriangle className="w-3 h-3" aria-hidden="true" /> Not searchable yet — upload it again
                    </p>
                  )}
                </div>
                <div className="flex gap-1">
                  <button type="button" className={buttonClass} disabled={busyId !== null} onClick={() => moveOut(doc)}>
                    <FolderOutput className="w-3 h-3" aria-hidden="true" />
                    {busyId === doc.id ? "Working…" : "Move to No project"}
                  </button>
                  <button type="button" className={`${buttonClass} text-destructive hover:bg-destructive/10`}
                    disabled={busyId !== null} onClick={() => remove(doc)} aria-label={`Delete ${doc.filename}`}>
                    <Trash2 className="w-3 h-3" aria-hidden="true" /> Delete
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {!project.archived && (
        <DocumentUpload onUpload={handleUpload} uploading={uploading} showProjectPicker={false} />
      )}
    </section>
  );
}

function ChatsSection({ project }) {
  return (
    <section aria-labelledby="chats-heading" className={cardClass}>
      <h2 id="chats-heading" className="text-lg font-semibold text-foreground mb-4">Chats ({project.chats.length})</h2>
      {project.chats.length === 0 ? (
        <div className="text-center py-8">
          <MessageSquare className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" aria-hidden="true" />
          <p className="text-sm text-muted-foreground mb-4">No chats yet.</p>
          {!project.archived && (
            <Link to={`/chat?project=${project.id}`} className={primaryButton}>
              <MessageSquarePlus className="w-4 h-4" aria-hidden="true" /> Start one
            </Link>
          )}
        </div>
      ) : (
        <ul className="space-y-2">
          {project.chats.map((chat) => {
            const last = parseServerTime(chat.last_message_time || chat.created_at);
            return (
              <li key={chat.id}>
                <Link to={`/chat?session=${chat.id}`}
                  className={`flex items-start gap-3 p-3 rounded-lg border border-transparent hover:bg-white/5 hover:border-border/50 transition-all ${focusRing}`}>
                  <MessageSquare className="w-4 h-4 mt-0.5 text-muted-foreground flex-shrink-0" aria-hidden="true" />
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium text-foreground truncate">{chat.title || `Chat ${chat.id}`}</span>
                    <span className="block text-xs text-muted-foreground">
                      {chat.topic && chat.topic !== "General" ? `${chat.topic} · ` : ""}
                      {last ? formatRelativeTime(last) : "No messages yet"}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
