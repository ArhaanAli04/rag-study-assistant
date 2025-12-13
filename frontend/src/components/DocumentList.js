import { FileText, Trash2, Calendar, FileType } from "lucide-react";

export default function DocumentList({ documents, onDelete }) {
  
  const formatDate = (dateString) => {
    if (!dateString) return 'Recently uploaded';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown';
    const mb = bytes / (1024 * 1024);
    if (mb < 1) {
      return `${(bytes / 1024).toFixed(2)} KB`;
    }
    return `${mb.toFixed(2)} MB`;
  };

  const getFileIcon = (filename) => {
    const ext = filename.toLowerCase().split('.').pop();
    switch(ext) {
      case 'pdf':
        return '📄';
      case 'pptx':
        return '📊';
      case 'docx':
        return '📝';
      default:
        return '📄';
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="glass border border-border/50 rounded-xl p-4 hover:border-primary/50 transition-all group"
        >
          {/* File Icon & Name */}
          <div className="flex items-start gap-3 mb-3">
            <div className="text-3xl">{getFileIcon(doc.path || doc.filename)}</div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-foreground truncate">
                {doc.filename || doc.path?.split('/').pop() || 'Unknown'}
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                {formatFileSize(doc.file_size)}
              </p>
            </div>
          </div>

          {/* Metadata */}
          <div className="space-y-2 mb-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Calendar className="w-3 h-3" />
              <span>{formatDate(doc.created_at )}</span>
            </div>
            {doc.version && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <FileType className="w-3 h-3" />
                <span>Version {doc.version} </span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => onDelete(doc.id)}
              className="p-2 hover:bg-destructive/20 rounded-lg transition-all group-hover:opacity-100 opacity-0"
              title="Delete document"
            >
              <Trash2 className="w-4 h-4 text-destructive" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
