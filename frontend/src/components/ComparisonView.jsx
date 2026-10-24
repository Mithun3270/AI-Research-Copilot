import React, { useMemo, useState } from 'react';
import {
  Scale,
  CheckCircle,
  Copy,
  Download,
  AlertCircle,
  Sparkles,
  CheckSquare,
  Square,
  X,
} from 'lucide-react';
import { api } from '../services/api';

const parameterGroups = [
  { title: 'Methodology', keys: ['methodology'] },
  { title: 'AI Models', keys: ['ai_models'] },
  { title: 'Dataset', keys: ['dataset'] },
  { title: 'Metrics and Results', keys: ['metrics', 'key_results'] },
  { title: 'Limitations and Trade-offs', keys: ['limitations', 'trade_offs'] },
];

const parameterLabels = {
  research_problem: 'Research Problem',
  methodology: 'Methodology',
  dataset: 'Dataset',
  ai_models: 'AI Models Used',
  metrics: 'Evaluation Metrics',
  key_results: 'Key Results',
  limitations: 'Limitations',
  trade_offs: 'Trade-offs',
};

function asLines(value) {
  if (value === 'NOT_FOUND' || value === null || value === undefined) return [];
  const values = Array.isArray(value) ? value : [value];
  return values.flatMap((item) => String(item).split(/\r?\n/))
    .map((line) => line.trim())
    .filter((line) => line && line.toUpperCase() !== 'NOT_FOUND')
    .slice(0, 2);
}

function missingMessage(key, bothMissing) {
  if (bothMissing) return 'Not mentioned in either paper.';
  if (key === 'dataset') return 'This paper does not mention any dataset.';
  if (key === 'ai_models') return 'This paper does not mention any AI model.';
  return 'Not mentioned in this paper.';
}

function renderValue(parameter, paperKey) {
  const lines = asLines(parameter[paperKey].value);
  const bothMissing = !asLines(parameter.paper_a.value).length
    && !asLines(parameter.paper_b.value).length;
  if (!lines.length) {
    return <span className="comparison-missing">{missingMessage(parameter.key, bothMissing)}</span>;
  }
  return (
    <>
      {lines.map((line, index) => <span className="comparison-value-line" key={index}>{line}</span>)}
      {parameter[paperKey].pages?.length > 0 && (
        <span className="comparison-source">
          Source: page {parameter[paperKey].pages.join(', ')}
        </span>
      )}
    </>
  );
}

function ParameterCard({ pair, group }) {
  const parameters = pair.parameters.filter((parameter) => group.keys.includes(parameter.key));
  return (
    <section className="comparison-result-section">
      <h3>{group.title}</h3>
      <div className="comparison-paper-columns">
        {[
          { key: 'paper_a', title: `Paper A: ${pair.papers[0].name}` },
          { key: 'paper_b', title: `Paper B: ${pair.papers[1].name}` },
        ].map((paper) => (
          <div className="comparison-paper-column" key={paper.key}>
            <h4 title={paper.title}>{paper.title}</h4>
            <ul className="comparison-evidence-list">
              {parameters.map((parameter) => (
                <li key={parameter.key}>
                  <strong>{parameter.label}:</strong> {renderValue(parameter, paper.key)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {group.title === 'AI Models' && (
        <ul className="comparison-model-summary">
          <li>Used only in {pair.papers[0].name}: {pair.model_comparison.used_only_paper_a.join(', ') || 'None identified.'}</li>
          <li>Used only in {pair.papers[1].name}: {pair.model_comparison.used_only_paper_b.join(', ') || 'None identified.'}</li>
          <li>Used in both: {pair.model_comparison.used_in_both.join(', ') || 'None identified.'}</li>
        </ul>
      )}
    </section>
  );
}

export default function ComparisonView({
  papers,
  selectedPapers,
  comparisonResult,
  setComparisonState,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const getPaperSector = (paper) => paper.sector || 'Other';
  const firstSelectedPaper = papers.find((paper) => selectedPapers.includes(paper.name));
  const selectedSector = firstSelectedPaper ? getPaperSector(firstSelectedPaper) : null;
  const groupedPapers = useMemo(() => {
    const groups = new Map();
    for (const paper of papers) {
      const sector = paper.sector || 'Other';
      if (!groups.has(sector)) groups.set(sector, []);
      groups.get(sector).push(paper);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [papers]);
  const selectionIsComparable = selectedPapers.length >= 2
    && selectedPapers.every((name) => {
      const paper = papers.find((item) => item.name === name);
      return paper && getPaperSector(paper) === selectedSector;
    });

  const togglePaper = (paper) => {
    setComparisonState((current) => {
      if (current.selectedPapers.includes(paper.name)) {
        return {
          ...current,
          selectedPapers: current.selectedPapers.filter((name) => name !== paper.name),
        };
      }
      if (current.selectedPapers.length > 0 && getPaperSector(paper) !== selectedSector) {
        return current;
      }
      return { ...current, selectedPapers: [...current.selectedPapers, paper.name] };
    });
    setError(null);
  };

  const handleCompare = async () => {
    if (!selectionIsComparable) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.comparePapers(selectedPapers, true);
      const pairs = response?.comparison?.pairs;
      if (!Array.isArray(response?.comparison?.papers)
        || response.comparison.papers.length !== selectedPapers.length
        || !Array.isArray(pairs)
        || pairs.length === 0
        || pairs.some((pair) => !Array.isArray(pair.papers)
          || pair.papers.length !== 2
          || !Array.isArray(pair.parameters)
          || pair.parameters.length !== 8)) {
        throw new Error('The comparison response was incomplete. Please retry the comparison.');
      }
      setComparisonState((current) => ({ ...current, comparisonResult: response }));
    } catch (err) {
      setError(err.message || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setComparisonState({ selectedPapers: [], comparisonResult: null });
    setError(null);
  };

  const serializedComparison = comparisonResult?.comparison
    ? JSON.stringify(comparisonResult.comparison, null, 2)
    : '';

  const handleCopy = () => {
    if (!serializedComparison) return;
    navigator.clipboard.writeText(serializedComparison);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!serializedComparison) return;
    const blob = new Blob([serializedComparison], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `paper_comparison_${Date.now()}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const comparison = comparisonResult?.comparison;
  const comparisonPairs = comparison?.pairs || [];
  const resultPaperCount = comparison?.papers?.length || 0;

  return (
    <div className="view-container animate-fade-in">
      <div className="view-header-bar glass-panel">
        <div>
          <h2>Multi-Paper Comparator</h2>
          <p className="view-subtitle">
            Compare research problems, methods, datasets, models, results, and limitations using retrieved paper evidence.
          </p>
        </div>
        <div className="comparison-header-actions">
          <button
            id="btn-clear-comparison"
            className="btn btn-secondary"
            onClick={handleClear}
          >
            <X size={16} />
            <span>Clear Comparison</span>
          </button>
          <button
            id="btn-run-comparison"
            className="btn btn-primary"
            onClick={handleCompare}
            disabled={loading || !selectionIsComparable}
          >
            <Scale size={16} />
            <span>{loading ? 'Comparing...' : `Compare (${selectedPapers.length} Papers)`}</span>
          </button>
        </div>
      </div>

      <div className="selection-card glass-panel">
        <div className="selection-title">
          {selectedSector
            ? `Select papers from ${selectedSector}:`
            : 'Select at least 2 papers from the same sector:'}
        </div>
        {groupedPapers.map(([sector, sectorPapers]) => (
          <section key={sector} className="comparison-sector-group">
            <h3 className="comparison-sector-heading">{sector} ({sectorPapers.length})</h3>
            <div className="paper-checkbox-grid">
              {sectorPapers.map((paper) => {
                const isSelected = selectedPapers.includes(paper.name);
                const isDisabled = Boolean(selectedSector && sector !== selectedSector);
                return (
                  <button
                    key={paper.name}
                    type="button"
                    className={`paper-checkbox-item glass-panel ${isSelected ? 'selected' : ''} ${isDisabled ? 'disabled' : ''}`}
                    onClick={() => togglePaper(paper)}
                    disabled={isDisabled}
                    title={isDisabled ? 'Only papers from the same sector can be compared.' : undefined}
                    aria-pressed={isSelected}
                  >
                    {isSelected ? (
                      <CheckSquare size={18} className="text-indigo shrink-0" />
                    ) : (
                      <Square size={18} className="text-muted shrink-0" />
                    )}
                    <div className="checkbox-label-wrap">
                      <div className="checkbox-paper-name" title={paper.name}>{paper.name}</div>
                      <div className="checkbox-paper-sub font-mono">
                        {paper.pages} pages • {paper.chunks} chunks
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {error && (
        <div className="error-banner glass-panel" role="alert">
          <AlertCircle size={18} className="text-rose" />
          <span>{error}</span>
        </div>
      )}

      {comparisonResult && !comparisonPairs.length && !loading && (
        <div className="error-banner glass-panel" role="alert">
          <AlertCircle size={18} className="text-rose" />
          <span>Saved comparison data is incomplete. Clear the comparison and run it again.</span>
        </div>
      )}

      {loading && (
        <div className="loading-container glass-panel" role="status">
          <div className="loading-spinner">
            <Sparkles size={32} className="animate-spin text-indigo" />
          </div>
          <h3>Synthesizing Multi-Paper Comparison</h3>
          <p className="text-secondary">
            Retrieving and comparing evidence for {selectedPapers.length} papers in the {selectedSector} sector...
          </p>
        </div>
      )}

      {comparisonPairs.length > 0 && !loading && (
        <div className="analysis-result-card glass-panel animate-fade-in">
          <div className="result-card-header">
            <div className="result-title">
              <Scale size={20} className="text-indigo" />
              <span>Comparative Synthesis ({resultPaperCount} Papers)</span>
            </div>
            <div className="result-actions">
              <button
                id="btn-copy-comparison"
                className="btn btn-secondary btn-sm"
                onClick={handleCopy}
              >
                {copied ? <CheckCircle size={14} className="text-emerald" /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy Synthesis'}</span>
              </button>
              <button
                id="btn-download-comparison"
                className="btn btn-secondary btn-sm"
                onClick={handleDownload}
              >
                <Download size={14} />
                <span>Download Report</span>
              </button>
            </div>
          </div>

          <div className="comparison-result-content">
            {comparisonPairs.map((pair) => (
              <div className="comparison-pair-result" key={pair.papers.map((paper) => paper.name).join('::')}>
                <section className="comparison-result-section">
                  <h3>Comparative Overview</h3>
                  <div className="table-wrapper">
                    <table className="comparison-table">
                      <thead>
                        <tr>
                          <th>Parameter</th>
                          <th>Paper A: {pair.papers[0].name}</th>
                          <th>Paper B: {pair.papers[1].name}</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pair.parameters.map((parameter) => (
                          <tr key={parameter.key}>
                            <th>{parameterLabels[parameter.key] || parameter.label}</th>
                            <td>{renderValue(parameter, 'paper_a')}</td>
                            <td>{renderValue(parameter, 'paper_b')}</td>
                            <td>
                              <span className={`comparison-status comparison-status-${parameter.status.toLowerCase()}`}>
                                {parameter.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {parameterGroups.map((group) => (
                  <ParameterCard key={group.title} pair={pair} group={group} />
                ))}

                <section className="comparison-result-section">
                  <h3>Synthesis</h3>
                  <p className="comparison-synthesis-text">{pair.synthesis}</p>
                </section>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
