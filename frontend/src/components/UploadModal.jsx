import React, { useState, useRef } from 'react';
import {
  X,
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import { api } from '../services/api';

export default function UploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (file) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF research papers are supported.');
      setSelectedFile(null);
      return;
    }
    setError(null);
    setResult(null);
    setSelectedFile(file);
  };

  const handleUploadAndIndex = async () => {
    if (!selectedFile || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const res = await api.uploadPaper(selectedFile);
      setResult(res.data);
      onUploadSuccess();
    } catch (err) {
      setError(err.message || 'Failed to upload and index document');
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="modal-backdrop animate-fade-in" onClick={onClose}>
      <div
        className="modal-card glass-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Upload size={20} className="text-indigo" />
            <h3>Index New Research Paper</h3>
          </div>
          <button
            id="btn-close-modal"
            className="btn-action-icon"
            onClick={onClose}
            disabled={uploading}
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {!result ? (
            <>
              {/* Drag and drop dropzone */}
              <div
                className={`dropzone-container ${dragActive ? 'active' : ''} ${selectedFile ? 'has-file' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  id="pdf-file-input"
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden-file-input"
                  onChange={(e) => e.target.files && handleFileSelect(e.target.files[0])}
                  disabled={uploading}
                />

                {selectedFile ? (
                  <div className="selected-file-info">
                    <FileText size={40} className="text-indigo animate-bounce-subtle" />
                    <div className="selected-file-name">{selectedFile.name}</div>
                    <div className="selected-file-size font-mono">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </div>
                    <div className="selected-file-action">Click or drop to replace</div>
                  </div>
                ) : (
                  <div className="dropzone-empty">
                    <Upload size={36} className="text-muted" />
                    <div className="dropzone-text">
                      Drag & Drop your research paper PDF here
                    </div>
                    <div className="dropzone-sub">or click to browse local files</div>
                  </div>
                )}
              </div>

              {/* Dynamic Indexing Explanation */}
              <div className="indexing-pipeline-info">
                <div className="pipeline-step">
                  <span className="step-num">1</span>
                  <span>Extract PDF Text (PyMuPDF)</span>
                </div>
                <ArrowRight size={14} className="text-muted" />
                <div className="pipeline-step">
                  <span className="step-num">2</span>
                  <span>500-Word Chunks</span>
                </div>
                <ArrowRight size={14} className="text-muted" />
                <div className="pipeline-step">
                  <span className="step-num">3</span>
                  <span>SentenceTransformer (384d)</span>
                </div>
                <ArrowRight size={14} className="text-muted" />
                <div className="pipeline-step">
                  <span className="step-num">4</span>
                  <span>Append to FAISS</span>
                </div>
              </div>

              {error && (
                <div className="error-banner glass-panel">
                  <AlertCircle size={16} className="text-rose shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {uploading && (
                <div className="uploading-state glass-panel animate-fade-in">
                  <Sparkles size={24} className="animate-spin text-indigo" />
                  <div className="uploading-text">
                    <div className="uploading-title">Processing & Indexing Paper...</div>
                    <div className="uploading-sub text-muted">
                      Extracting text pages, generating vector embeddings, and updating FAISS index
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="upload-success-state animate-fade-in">
              <div className="success-icon-wrap">
                <CheckCircle size={44} className="text-emerald" />
              </div>
              <h3>Paper Successfully Indexed!</h3>
              <p className="text-secondary">
                The document is now part of the active FAISS vector index and immediately available for RAG research queries.
              </p>

              <div className="indexing-stats-grid glass-panel">
                <div className="idx-stat">
                  <span className="idx-label">Document:</span>
                  <span className="idx-val font-semibold idx-document-name" title={result.paper}>
                    {result.paper}
                  </span>
                </div>
                <div className="idx-stat">
                  <span className="idx-label">Pages Extracted:</span>
                  <span className="idx-val font-mono">{result.pages}</span>
                </div>
                <div className="idx-stat">
                  <span className="idx-label">Category:</span>
                  <span className="idx-val">{result.category || result.sector || 'Uncategorized'}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {!result ? (
            <>
              <button
                className="btn btn-secondary"
                onClick={onClose}
                disabled={uploading}
              >
                Cancel
              </button>
              <button
                id="btn-confirm-upload"
                className="btn btn-primary"
                onClick={handleUploadAndIndex}
                disabled={!selectedFile || uploading}
              >
                <Sparkles size={15} />
                <span>{uploading ? 'Indexing into FAISS...' : 'Index Paper'}</span>
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-secondary" onClick={handleReset}>
                Index Another Paper
              </button>
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
