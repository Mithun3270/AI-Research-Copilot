import React from 'react';
import { BookOpen, Cpu, Database, Server, RefreshCw, Upload } from 'lucide-react';

export default function Header({ health, papersCount, onOpenUpload, onRefresh, loading }) {
  const ollamaOk = health?.ollama?.online && health?.ollama?.model_available;
  const faissOk = health?.vector_database?.synchronized;

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="logo-container">
          <div className="logo-icon-wrap">
            <BookOpen className="logo-icon" size={22} />
          </div>
          <div>
            <div className="brand-title">
              AI Research <span className="text-gradient">Copilot</span>
            </div>
            <div className="brand-subtitle">
              Local RAG Research Suite & Academic Intelligence
            </div>
          </div>
        </div>
      </div>

      <div className="header-center">
        <div className="system-health-bar glass-panel">
          {/* Embedding Model */}
          <div className="health-pill" title="Local SentenceTransformers embedding model">
            <Cpu size={14} className="text-indigo" />
            <span className="pill-label">Model:</span>
            <span className="pill-val">all-MiniLM-L6 (384d)</span>
          </div>

          <div className="health-divider" />

          {/* FAISS Index */}
          <div className="health-pill" title="FAISS Vector Database">
            <Database size={14} className="text-cyan" />
            <span className="pill-label">FAISS:</span>
            <span className="pill-val font-mono">{health?.vector_database?.total_vectors ?? 0} vectors</span>
          </div>

          <div className="health-divider" />

          {/* Ollama LLM */}
          <div className="health-pill" title="Local LLM via Ollama">
            <Server size={14} className={ollamaOk ? 'text-emerald' : 'text-amber'} />
            <div className={`status-dot ${ollamaOk ? 'online' : ''}`} />
            <span className="pill-val">{health?.ollama?.model ?? 'qwen2.5:3b'}</span>
          </div>
        </div>
      </div>

      <div className="header-right">
        <button
          id="btn-refresh-health"
          onClick={onRefresh}
          className="btn btn-outline btn-icon"
          title="Refresh status and papers"
          disabled={loading}
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>

        <button
          id="btn-upload-paper-header"
          onClick={onOpenUpload}
          className="btn btn-primary"
        >
          <Upload size={15} />
          <span>Upload Paper</span>
        </button>
      </div>
    </header>
  );
}
