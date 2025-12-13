import { useState, useRef } from "react";
import { Upload, FileText, X, AlertCircle } from "lucide-react";

export default function DocumentUpload({ onUpload, uploading }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

  const allowedTypes = ['.pdf', '.pptx', '.docx'];
  const maxSizeMB = 50;

  const validateFile = (file) => {
    // Check file type
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedTypes.includes(extension)) {
      return `Invalid file type. Allowed: ${allowedTypes.join(', ')}`;
    }

    // Check file size
    const sizeMB = file.size / (1024 * 1024);
    if (sizeMB > maxSizeMB) {
      return `File too large (${sizeMB.toFixed(1)} MB). Max ${maxSizeMB} MB.`;
    }

    return null;
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    setUploadError(null);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const error = validateFile(file);
      
      if (error) {
        setUploadError(error);
        return;
      }
      
      setSelectedFile(file);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    setUploadError(null);

    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const error = validateFile(file);
      
      if (error) {
        setUploadError(error);
        return;
      }
      
      setSelectedFile(file);
    }
  };

  const handleUploadClick = async () => {
    if (!selectedFile) return;

    try {
      await onUpload(selectedFile);
      setSelectedFile(null);
      setUploadError(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setUploadError(err.message);
    }
  };

  const handleCancel = () => {
    setSelectedFile(null);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="glass border border-border/50 rounded-2xl p-6">
      <h3 className="text-lg font-semibold text-foreground mb-4">Upload Document</h3>

      {/* Drag & Drop Area */}
      <div
        className={`
          relative border-2 border-dashed rounded-xl p-8 text-center transition-all
          ${dragActive ? 'border-primary bg-primary/5' : 'border-border/50'}
          ${selectedFile ? 'bg-primary/5 border-primary' : ''}
        `}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.pptx,.docx"
          onChange={handleChange}
          className="hidden"
          id="file-upload"
          disabled={uploading}
        />

        {!selectedFile ? (
          <>
            <Upload className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h4 className="text-lg font-medium text-foreground mb-2">
              Drop your file here, or browse
            </h4>
            <p className="text-sm text-muted-foreground mb-4">
              Supports PDF, PPTX, DOCX up to 50 MB
            </p>
            <label
              htmlFor="file-upload"
              className="inline-block px-6 py-3 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all cursor-pointer"
            >
              Browse Files
            </label>
          </>
        ) : (
          <div className="flex items-center justify-between bg-white/5 rounded-lg p-4">
            <div className="flex items-center gap-3">
              <FileText className="w-8 h-8 text-primary" />
              <div className="text-left">
                <p className="text-sm font-medium text-foreground">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
            </div>
            <button
              onClick={handleCancel}
              className="p-2 hover:bg-white/5 rounded-lg transition-all"
              disabled={uploading}
            >
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        )}
      </div>

      {/* Error Message */}
      {uploadError && (
        <div className="mt-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
          <p className="text-sm text-destructive">{uploadError}</p>
        </div>
      )}

      {/* Upload Button */}
      {selectedFile && (
        <div className="mt-4 flex justify-end gap-3">
          <button
            onClick={handleCancel}
            className="px-4 py-2 rounded-lg hover:bg-white/5 transition-all text-foreground"
            disabled={uploading}
          >
            Cancel
          </button>
          <button
            onClick={handleUploadClick}
            disabled={uploading}
            className="px-6 py-2 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
        </div>
      )}
    </div>
  );
}
