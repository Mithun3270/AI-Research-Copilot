import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  Copy,
  Download,
  ExternalLink,
  FileSearch,
  MessageCircle,
  Sparkles,
} from 'lucide-react';
import mermaid from 'mermaid';
import { api } from '../services/api';

mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'dark' });

const reportSections = [
  ['problem_statement', 'Problem Statement'],
  ['proposed_method', 'Proposed Method'],
  ['system_architecture', 'System Architecture'],
  ['mathematical_models', 'Mathematical Models'],
  ['dataset', 'Dataset'],
  ['metrics', 'Metrics'],
  ['results', 'Results'],
  ['strengths', 'Strengths'],
  ['limitations', 'Limitations'],
  ['future_work', 'Future Work'],
];

function ArchitectureDiagram({ architecture, paperId, architectureText }) {
  const [svg, setSvg] = useState('');
  const [useListFallback, setUseListFallback] = useState(false);
  const [retryError, setRetryError] = useState('');
  const renderId = useRef(0);

  useEffect(() => {
    if (architecture?.kind !== 'generated') return undefined;

    let cancelled = false;

    const renderDiagram = async (diagram, retriesRemaining) => {
      try {
        const nodeIds = new Set(
          [...diagram.mermaid.matchAll(/(?:^|[\s;])([A-Za-z][A-Za-z0-9_]*)\s*(?=[\x5B({])/g)]
            .map((match) => match[1]),
        );
        if (nodeIds.size < 5 || nodeIds.size > 8) {
          throw new Error('The architecture diagram must contain 5 to 8 boxes.');
        }
        await mermaid.parse(diagram.mermaid);
        const result = await mermaid.render(`paper-architecture-${++renderId.current}`, diagram.mermaid);
        if (!cancelled) setSvg(result.svg);
      } catch (error) {
        if (retriesRemaining > 0) {
          try {
            const repaired = await api.regenerateArchitecture(paperId, diagram.mermaid);
            await renderDiagram(repaired, retriesRemaining - 1);
          } catch (retryFailure) {
            if (!cancelled) {
              setRetryError(retryFailure.message || 'Architecture retry failed.');
              setUseListFallback(true);
            }
          }
        } else if (!cancelled) {
          setRetryError(error.message || 'Mermaid syntax is invalid.');
          setUseListFallback(true);
        }
      }
    };

    renderDiagram(architecture, 1);
    return () => {
      cancelled = true;
    };
  }, [architecture, paperId]);

  if (architecture?.kind === 'original') {
    return (
      <div className="architecture-figure">
        <p className="architecture-label">Original figure from the paper (page {architecture.page})</p>
        <img src={architecture.image_data} alt="Original architecture figure extracted from the selected paper" />
      </div>
    );
  }

  const steps = architecture?.steps?.length
    ? architecture.steps
    : architectureText && architectureText !== 'Not mentioned in the paper'
      ? [architectureText]
      : ['Not mentioned in the paper'];

  return (
    <div className="architecture-figure">
      <p className="architecture-label">AI-generated architecture (based on the paper text)</p>
      {useListFallback ? (
        <>
          {retryError && <p className="architecture-retry-error">{retryError}</p>}
          <ol className="architecture-step-list">
            {steps.map((step, index) => <li key={index}>{step}</li>)}
          </ol>
        </>
      ) : (
        <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />
      )}
    </div>
  );
}

export default function AnalysisView({ papers, initialPaper, onAskInChat }) {
  const [selectedPaper, setSelectedPaper] = useState(
    initialPaper && papers.some((paper) => paper.id === initialPaper || paper.name === initialPaper)
      ? initialPaper
      : papers[0]?.id || papers[0]?.name || '',
  );
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [diagramVersion, setDiagramVersion] = useState(0);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const currentPaperMeta = papers.find((paper) => paper.id === selectedPaper || paper.name === selectedPaper);

  const handleAnalyze = async () => {
    if (!selectedPaper) return;
    setLoading(true);
    setError('');
    setAnalysisResult(null);
    try {
      const result = await api.analyzePaper(selectedPaper);
      setAnalysisResult(result);
      setDiagramVersion((version) => version + 1);
    } catch (analysisError) {
      setError(analysisError.message || 'Failed to analyze the selected paper.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!analysisResult) return;
    const text = reportSections
      .map(([key, label]) => `${label}\n${analysisResult.analysis[key]}`)
      .join('\n\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async () => {
    if (!analysisResult || downloading) return;
    setDownloading(true);
    setError('');
    try {
      const blob = await api.downloadAnalysisPdf({
        paper_id: analysisResult.paper_id,
        analysis: analysisResult.analysis,
        architecture: analysisResult.architecture,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `analysis_${analysisResult.paper_id.replace(/\.pdf$/i, '')}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (downloadError) {
      setError(downloadError.message || 'Failed to download the analysis report.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="view-container animate-fade-in">
      <div className="view-header-bar glass-panel">
        <div>
          <h2>Automated Paper Analysis</h2>
          <p className="view-subtitle">
            Generate a complete, evidence-based report for one selected paper.
          </p>
        </div>
        <div className="view-header-controls">
          <select
            id="analysis-paper-select"
            className="select-control"
            value={selectedPaper}
            onChange={(event) => {
              setSelectedPaper(event.target.value);
              setAnalysisResult(null);
              setError('');
            }}
            disabled={loading || papers.length === 0}
          >
            {papers.length === 0 && <option value="">No indexed papers</option>}
            {papers.map((paper) => {
              const paperId = paper.id || paper.name;
              return (
                <option key={paperId} value={paperId}>
                  {paper.name} ({paper.pages} pages)
                </option>
              );
            })}
          </select>
          <button
            id="btn-run-analysis"
            className="btn btn-primary"
            onClick={handleAnalyze}
            disabled={loading || !selectedPaper}
          >
            <FileSearch size={16} />
            <span>{loading ? 'Analyzing Paper...' : 'Run Deep Analysis'}</span>
          </button>
        </div>
      </div>

      {currentPaperMeta && (
        <div className="meta-banner glass-panel">
          <div className="meta-pill">
            <span className="meta-label">Selected Paper:</span>
            <span className="meta-val font-semibold">{currentPaperMeta.name}</span>
          </div>
          <div className="meta-pill">
            <span className="meta-label">Pages:</span>
            <span className="meta-val font-mono">{currentPaperMeta.pages}</span>
          </div>
          <a
            href={api.getPaperFileUrl(currentPaperMeta.name)}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary btn-sm"
          >
            <span>View PDF</span>
            <ExternalLink size={13} />
          </a>
        </div>
      )}

      {error && (
        <div className="error-banner glass-panel">
          <AlertCircle size={18} className="text-rose" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="loading-container glass-panel">
          <div className="loading-spinner">
            <Sparkles size={32} className="animate-spin text-indigo" />
          </div>
          <h3>Analyzing the selected paper</h3>
          <p className="text-secondary">
            Reading all indexed chunks from “{currentPaperMeta?.name || selectedPaper}” only.
          </p>
        </div>
      )}

      {analysisResult && !loading && (
        <div className="analysis-result-card glass-panel animate-fade-in">
          <div className="result-card-header">
            <div className="result-title">
              <BookOpen size={20} className="text-indigo" />
              <span>Analysis Report: {analysisResult.paper}</span>
            </div>
            <div className="result-actions">
              <button className="btn btn-secondary btn-sm" onClick={handleCopy}>
                <Copy size={14} />
                <span>{copied ? 'Copied' : 'Copy Report'}</span>
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={handleDownload}
                disabled={downloading}
              >
                <Download size={14} />
                <span>{downloading ? 'Preparing PDF...' : 'Download report'}</span>
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onAskInChat?.(analysisResult.paper_id)}
              >
                <MessageCircle size={14} />
                <span>Ask follow-up in Chat</span>
              </button>
            </div>
          </div>

          <section className="analysis-architecture-card">
            <h3>Architecture</h3>
            <ArchitectureDiagram
              key={diagramVersion}
              architecture={analysisResult.architecture}
              paperId={analysisResult.paper_id}
              architectureText={analysisResult.analysis.system_architecture}
            />
          </section>

          <div className="analysis-report-grid">
            {reportSections.map(([key, label]) => (
              <section className="analysis-report-section" key={key}>
                <h3>{label}</h3>
                <p>{analysisResult.analysis[key] || 'Not mentioned in the paper'}</p>
              </section>
            ))}
          </div>
          <p className="analysis-chunks-count">
            Analyzed all {analysisResult.total_chunks_analyzed} indexed chunks from this paper.
          </p>
        </div>
      )}

      {!analysisResult && !loading && !error && (
        <div className="empty-placeholder-card glass-panel">
          <FileSearch size={48} className="text-muted" />
          <h3>Select one paper and run a deep analysis</h3>
          <p>The report uses only the selected paper’s indexed content. Sections absent from the paper are marked explicitly.</p>
        </div>
      )}
    </div>
  );
}
