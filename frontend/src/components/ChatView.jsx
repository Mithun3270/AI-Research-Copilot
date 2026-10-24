import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  Bot,
  User,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Download,
  SlidersHorizontal,
  ExternalLink,
} from 'lucide-react';
import { api } from '../services/api';

const depthOptions = {
  Quick: 3,
  Balanced: 5,
  Deep: 10,
};

export default function ChatView({ papers, categories = [], initialPaper, onInitialPaperApplied }) {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '👋 Welcome to your **AI Research Copilot**.\n\nI am grounded strictly in your local research papers indexed in FAISS (`vector_db/research.index`) and powered by Ollama (`qwen2.5:3b`).\n\nAsk me anything about water quality monitoring architectures, edge AI models, sensor calibration, or comparative methodology. Every answer includes verified page citations.',
      sources: [],
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);

  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedPaper, setSelectedPaper] = useState(
    papers.some((paper) => paper.name === initialPaper) ? initialPaper : 'ALL',
  );
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [searchDepth, setSearchDepth] = useState('Balanced');
  const [copiedId, setCopiedId] = useState(null);
  const [expandedSourceMsgId, setExpandedSourceMsgId] = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  const messagesEndRef = useRef(null);
  const topK = depthOptions[searchDepth];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (initialPaper && papers.some((paper) => paper.name === initialPaper)) {
      onInitialPaperApplied?.();
    }
  }, [initialPaper, onInitialPaperApplied, papers]);

  const suggestedQuestions = [
    'What edge AI models and algorithms are used for water quality prediction?',
    'What sensors are integrated in the AIoT monitoring architecture?',
    'What are the key limitations and research gaps reported in the papers?',
    'How does XGBoost compare with other ML algorithms for WQI forecasting?',
  ];

  const handleSend = async (questionText = null) => {
    const query = (questionText || inputQuery).trim();
    if (!query || loading) return;

    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery('');
    setLoading(true);

    try {
      const paperFilter = selectedPaper === 'ALL' ? null : [selectedPaper];
      const categoryFilter = selectedCategory === 'ALL' ? null : [selectedCategory];
      const res = await api.ask(query, topK, paperFilter, false, categoryFilter);

      const botMsg = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer || 'No response received from engine.',
        sources: res.sources || [],
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      const errorMsg = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `⚠️ **Error querying engine**: ${err.message}\n\nPlease verify that Ollama is running (` + '`ollama serve`' + `) and the FastAPI backend is online.`,
        sources: [],
        timestamp: new Date().toLocaleTimeString(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDownload = (msg) => {
    const text = `QUESTION: ${msg.query || 'Research Query'}\n\nANSWER:\n${msg.content}\n\nSOURCES:\n` +
      msg.sources.map(s => `- ${s.paper} (Page ${s.page}, similarity ${s.score}):\n  ${s.text_snippet}`).join('\n\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `research_qa_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="chat-view-container">
      <div className="chat-grounding-banner glass-panel">
        <BookOpen size={16} />
        <span>Answers come only from your {papers.length} indexed papers</span>
      </div>

      <div className="chat-top-bar glass-panel">
        <div className="filter-group">
          <label htmlFor="paper-filter-select" className="filter-label">Target Corpus:</label>
          <select
            id="paper-filter-select"
            className="select-control"
            value={selectedPaper}
            onChange={(e) => setSelectedPaper(e.target.value)}
          >
            <option value="ALL">🌐 All Indexed Papers ({papers.length})</option>
            {papers.map((p) => (
              <option key={p.name} value={p.name}>
                📄 {p.name} ({p.pages} pp)
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="category-filter-select" className="filter-label">Category:</label>
          <select
            id="category-filter-select"
            className="select-control"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
          >
            <option value="ALL">All categories</option>
            {categories.map((category) => (
              <option key={category.name} value={category.name}>
                {category.name} ({category.paper_count})
              </option>
            ))}
          </select>
        </div>

        <div className="filter-actions">
          <button
            id="btn-toggle-chat-settings"
            className={`btn btn-secondary btn-sm ${showSettings ? 'active' : ''}`}
            onClick={() => setShowSettings(!showSettings)}
          >
            <SlidersHorizontal size={14} />
            <span>Search Depth</span>
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="chat-settings-drawer glass-panel animate-fade-in" role="group" aria-label="Search depth">
          {Object.entries(depthOptions).map(([label, count]) => (
            <button
              key={label}
              className={`search-depth-option ${searchDepth === label ? 'active' : ''}`}
              onClick={() => setSearchDepth(label)}
              aria-pressed={searchDepth === label}
            >
              <span>{label}{label === 'Balanced' ? ' (default)' : ''}</span>
              <span>{count} chunks</span>
            </button>
          ))}
        </div>
      )}

      {/* Suggested Questions */}
      <div className="suggested-prompts-row">
        <div className="suggested-label">
          <Sparkles size={14} className="text-amber" />
          <span>Quick Inquiries:</span>
        </div>
        <div className="chips-scroll">
          {suggestedQuestions.map((q, idx) => (
            <button
              key={idx}
              className="prompt-chip"
              onClick={() => handleSend(q)}
              disabled={loading}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Messages Stream */}
      <div className="messages-stream">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isSourceExpanded = expandedSourceMsgId === msg.id;

          return (
            <div
              key={msg.id}
              className={`message-row ${isUser ? 'user-row' : 'assistant-row'} animate-fade-in`}
            >
              <div className="message-avatar">
                {isUser ? <User size={18} /> : <Bot size={18} className="text-indigo" />}
              </div>

              <div className="message-card glass-panel">
                <div className="message-header">
                  <span className="message-sender">
                    {isUser ? 'Researcher' : 'Research Copilot'}
                  </span>
                  <span className="message-timestamp">{msg.timestamp}</span>

                  {!isUser && (
                    <div className="message-actions">
                      <button
                        className="btn-action-icon"
                        onClick={() => handleCopy(msg.content, msg.id)}
                        title="Copy to clipboard"
                      >
                        {copiedId === msg.id ? (
                          <Check size={14} className="text-emerald" />
                        ) : (
                          <Copy size={14} />
                        )}
                      </button>
                      <button
                        className="btn-action-icon"
                        onClick={() => handleDownload(msg)}
                        title="Download as report"
                      >
                        <Download size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {/* Message Body */}
                <div className="message-body markdown-content">
                  {msg.content.split('\n\n').map((para, pIdx) => {
                    // Check for headers or bullet points
                    if (para.startsWith('### ')) {
                      return <h3 key={pIdx}>{para.replace('### ', '')}</h3>;
                    }
                    if (para.startsWith('## ')) {
                      return <h2 key={pIdx}>{para.replace('## ', '')}</h2>;
                    }
                    if (para.startsWith('# ')) {
                      return <h1 key={pIdx}>{para.replace('# ', '')}</h1>;
                    }
                    return <p key={pIdx}>{para}</p>;
                  })}
                </div>

                {/* Sources & Citations Tray */}
                {!isUser && msg.sources && msg.sources.length > 0 && (
                  <div className="sources-tray">
                    <button
                      className="sources-header-toggle"
                      onClick={() =>
                        setExpandedSourceMsgId(isSourceExpanded ? null : msg.id)
                      }
                    >
                      <div className="sources-title">
                        <BookOpen size={14} className="text-cyan" />
                        <span>
                          {msg.sources.length} Verified Evidence Sources
                        </span>
                      </div>
                      {isSourceExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>

                    {/* Source Badges */}
                    <div className="source-badges-grid">
                      {msg.sources.map((s, sIdx) => (
                        <div key={sIdx} className="source-badge glass-panel">
                          <span className="source-paper-name" title={s.paper}>
                            📄 {s.paper}
                          </span>
                          <span className="badge badge-cyan font-mono">
                            p. {s.page}
                          </span>
                          <span className="badge badge-primary font-mono" title="Cosine similarity">
                            sim: {s.score}
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* Detailed Context Drawer */}
                    {isSourceExpanded && (
                      <div className="source-details-list animate-fade-in">
                        {msg.sources.map((s, sIdx) => (
                          <div key={sIdx} className="source-detail-card">
                            <div className="source-detail-head">
                              <span className="font-mono text-cyan font-semibold">
                                Source {sIdx + 1}: {s.paper} (Page {s.page})
                              </span>
                              <a
                                href={api.getPaperFileUrl(s.paper)}
                                target="_blank"
                                rel="noreferrer"
                                className="source-link"
                              >
                                View PDF <ExternalLink size={12} />
                              </a>
                            </div>
                            <div className="source-snippet font-mono">
                              "{s.text_snippet}"
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-row assistant-row animate-fade-in">
            <div className="message-avatar">
              <Bot size={18} className="text-indigo" />
            </div>
            <div className="message-card glass-panel loading-card">
              <div className="loading-status">
                <div className="status-dot online" />
                <span>Synthesizing answer from FAISS vectors & Ollama (qwen2.5:3b)...</span>
              </div>
              <div className="shimmer-line" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Query Input Box */}
      <div className="chat-input-area glass-panel">
        <textarea
          id="input-research-query"
          className="chat-textarea"
          placeholder="Ask any research question grounded in your papers... (Press Enter to submit, Shift+Enter for new line)"
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={2}
        />
        <div className="input-bar-actions">
          <span className="input-hint">
            Grounding: <strong>{selectedPaper === 'ALL' ? 'All Papers' : selectedPaper}</strong>
          </span>
          <button
            id="btn-send-query"
            className="btn btn-primary btn-send"
            onClick={() => handleSend()}
            disabled={loading || !inputQuery.trim()}
          >
            <Send size={15} />
            <span>Send Query</span>
          </button>
        </div>
      </div>
    </div>
  );
}
