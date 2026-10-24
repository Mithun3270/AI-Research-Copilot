import React, { useMemo, useState } from 'react';
import {
  Sparkles,
  CheckCircle,
  Copy,
  Download,
  AlertCircle,
  ShieldAlert,
  Lightbulb,
  Search,
} from 'lucide-react';
import { api } from '../services/api';

export default function ResearchGapsView({ papers }) {
  const [selectedPaper, setSelectedPaper] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [gapsResult, setGapsResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const filteredPapers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return papers.filter((paper) => (
      !query
      || paper.name.toLowerCase().includes(query)
      || (paper.category || paper.sector || '').toLowerCase().includes(query)
    ));
  }, [papers, searchQuery]);

  const selectedPaperDetails = papers.find((paper) => paper.id === selectedPaper);
  const gapsText = gapsResult ? JSON.stringify(gapsResult, null, 2) : '';

  const handleSelectPaper = (paperId) => {
    setSelectedPaper(paperId);
    setGapsResult(null);
    setError(null);
  };

  const handleDetectGaps = async () => {
    if (!selectedPaper || loading) return;
    setLoading(true);
    setError(null);
    setGapsResult(null);
    try {
      const result = await api.detectResearchGaps(selectedPaper, true);
      setGapsResult(result);
    } catch (err) {
      setError(err.message || 'Failed to detect research gaps');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!gapsText) return;
    await navigator.clipboard.writeText(gapsText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!gapsText) return;
    const blob = new Blob([gapsText], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `research_gaps_${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="view-container animate-fade-in">
      <div className="view-header-bar gap-header-bar glass-panel">
        <div>
          <h2>Research Gap &amp; Innovation Detector</h2>
          <p className="view-subtitle">
            Select one indexed paper to find evidence-backed limitations and research ideas.
          </p>
        </div>
        <div className="gap-header-actions">
          <div className="gap-analysis-scope glass-panel" aria-live="polite">
            <div className="banner-icon-wrap">
              <Lightbulb size={24} className="text-amber" />
            </div>
            <div className="banner-content">
              <div className="banner-title">
                {selectedPaperDetails ? `Analyzing: ${selectedPaperDetails.name}` : 'Analyzing: No paper selected'}
              </div>
              <div className="banner-desc">
                {selectedPaperDetails
                  ? `${selectedPaperDetails.category || selectedPaperDetails.sector || 'Uncategorized'} · ${selectedPaperDetails.pages} pages`
                  : 'Choose one paper above to enable gap analysis.'}
              </div>
            </div>
          </div>
          <button
            id="btn-run-gaps"
            className="btn btn-primary"
            onClick={handleDetectGaps}
            disabled={!selectedPaper || loading}
          >
            <Sparkles size={16} />
            <span>{loading ? 'Analyzing Paper...' : 'Discover Research Gaps'}</span>
          </button>
        </div>
      </div>

      <div className="gap-paper-picker glass-panel">
        <div className="gap-picker-header">
          <div>
            <h3>Select a paper</h3>
            <p className="text-secondary">Only the selected paper will be used as evidence.</p>
          </div>
          <label className="gap-paper-search">
            <Search size={15} className="text-muted" />
            <input
              type="search"
              aria-label="Search indexed papers"
              placeholder="Search papers or categories"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        </div>
        {filteredPapers.length > 0 ? (
          <div className="gap-paper-options">
            {filteredPapers.map((paper) => (
              <button
                key={paper.id}
                type="button"
                className={`gap-paper-option ${selectedPaper === paper.id ? 'active' : ''}`}
                aria-pressed={selectedPaper === paper.id}
                onClick={() => handleSelectPaper(paper.id)}
              >
                <span className="gap-paper-title" title={paper.name}>{paper.name}</span>
                <span className="gap-paper-meta">
                  {paper.category || paper.sector || 'Uncategorized'} · {paper.pages} pages
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-secondary">No indexed papers match your search.</p>
        )}
      </div>

      {error && (
        <div className="error-banner glass-panel" role="alert">
          <AlertCircle size={18} className="text-rose" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="loading-container glass-panel" aria-live="polite">
          <div className="loading-spinner">
            <Sparkles size={32} className="animate-spin text-amber" />
          </div>
          <h3>Analyzing the selected paper</h3>
          <p className="text-secondary">
            Retrieving its FAISS evidence and validating each proposed gap against the paper text...
          </p>
        </div>
      )}

      {gapsResult && !loading && (
        <div className="analysis-result-card glass-panel animate-fade-in">
          <div className="result-card-header">
            <div className="result-title">
              <ShieldAlert size={20} className="text-amber" />
              <span>Research Gaps for {gapsResult.paper}</span>
            </div>
            <div className="result-actions">
              <button id="btn-copy-gaps" className="btn btn-secondary btn-sm" onClick={handleCopy}>
                {copied ? <CheckCircle size={14} className="text-emerald" /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy JSON'}</span>
              </button>
              <button id="btn-download-gaps" className="btn btn-secondary btn-sm" onClick={handleDownload}>
                <Download size={14} />
                <span>Download JSON</span>
              </button>
            </div>
          </div>
          {gapsResult.gaps.length > 0 ? (
            <div className="research-gap-cards">
              {gapsResult.gaps.map((gap, index) => (
                <article className="research-gap-card glass-panel" key={`${gap.title}-${index}`}>
                  <div className="research-gap-card-header">
                    <h3>{gap.title}</h3>
                    <span className={`gap-severity gap-severity-${gap.severity.toLowerCase()}`}>
                      {gap.severity}
                    </span>
                  </div>
                  <div className="research-gap-field">
                    <h4>Why it is a problem</h4>
                    <p>{gap.why_it_is_a_problem}</p>
                  </div>
                  <div className="research-gap-field research-gap-evidence">
                    <h4>Evidence · Page {gap.page}</h4>
                    <blockquote>{gap.evidence}</blockquote>
                  </div>
                  <div className="research-gap-field">
                    <h4>Proposed research idea</h4>
                    <p>{gap.proposed_research_idea}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-placeholder-card glass-panel">
              <ShieldAlert size={36} className="text-muted" />
              <p>No evidence-supported research gaps were identified in this paper's retrieved passages.</p>
            </div>
          )}
        </div>
      )}

      {!gapsResult && !loading && (
        <div className="empty-placeholder-card glass-panel">
          <Sparkles size={48} className="text-amber" />
          <h3>Identify Open Challenges in One Paper</h3>
          <p>Select an indexed paper, then discover evidence-backed limitations and research ideas.</p>
        </div>
      )}
    </div>
  );
}
