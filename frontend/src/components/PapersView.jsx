import React, { useMemo, useState } from 'react';
import {
  Library,
  Trash2,
  ExternalLink,
  FileText,
  FileSearch,
  CheckCircle,
  AlertCircle,
  HardDrive,
  Layers,
} from 'lucide-react';
import { api } from '../services/api';

export default function PapersView({
  papers,
  sectors = [],
  categoryFilter = 'All',
  setCategoryFilter,
  onSelectPaperForAnalysis,
  onRefresh,
  onPaperDeleted,
}) {
  const [deletingName, setDeletingName] = useState(null);
  const [updatingSectorName, setUpdatingSectorName] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [deleteSuccess, setDeleteSuccess] = useState(null);
  const [collapsedSectors, setCollapsedSectors] = useState({});

  const sectorOptions = useMemo(() => (
    [...new Set([
      ...sectors,
      ...papers.map((paper) => paper.category || paper.sector).filter(Boolean),
    ])].sort((left, right) => left.localeCompare(right))
  ), [papers, sectors]);

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const handleDelete = async (paperName) => {
    if (!window.confirm(`Are you sure you want to delete '${paperName}' from the vector index and file storage?`)) {
      return;
    }

    setDeletingName(paperName);
    setDeleteError(null);
    setDeleteSuccess(null);

    try {
      await api.deletePaper(paperName, true);
      setDeleteSuccess(`'${paperName}' successfully removed from FAISS index and disk.`);
      onPaperDeleted?.(paperName);
      onRefresh();
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete paper');
    } finally {
      setDeletingName(null);
    }
  };

  const handleSectorChange = async (paperName, sector) => {
    let category = sector;
    if (category === '__create_new__') {
      category = window.prompt('Enter a name for the new research category:')?.trim();
      if (!category) return;
    }
    setUpdatingSectorName(paperName);
    setDeleteError(null);
    setDeleteSuccess(null);

    try {
      await api.updatePaperCategory(paperName, category);
      setDeleteSuccess(`'${paperName}' category updated to ${category}.`);
      await onRefresh();
    } catch (err) {
      setDeleteError(err.message || 'Failed to update paper sector');
    } finally {
      setUpdatingSectorName(null);
    }
  };

  const toggleSector = (sector) => {
    setCollapsedSectors((current) => ({
      ...current,
      [sector]: !current[sector],
    }));
  };

  const totalPages = papers.reduce((acc, p) => acc + (p.pages || 0), 0);
  const totalChunks = papers.reduce((acc, p) => acc + (p.chunks || 0), 0);
  const totalSize = papers.reduce((acc, p) => acc + (p.file_size || 0), 0);
  const visiblePapers = categoryFilter === 'All'
    ? papers
    : papers.filter((paper) => (paper.category || paper.sector || 'Other') === categoryFilter);
  const papersBySector = sectorOptions.map((sector) => ({
    sector,
    papers: visiblePapers.filter((paper) => (paper.category || paper.sector || 'Other') === sector),
  })).filter((group) => group.papers.length > 0);

  return (
    <div className="view-container animate-fade-in">
      <div className="view-header-bar glass-panel">
        <div>
          <h2>Research Paper Repository</h2>
          <p className="view-subtitle">
            Manage local PDFs, review chunk distribution, open original documents, and maintain synchronized FAISS indices.
          </p>
        </div>
      </div>

      {/* Summary Stats Row */}
      <div className="repo-stats-grid">
        <div className="repo-stat-card glass-panel">
          <div className="repo-stat-icon-wrap bg-indigo-subtle">
            <Library size={22} className="text-indigo" />
          </div>
          <div>
            <div className="repo-stat-val font-mono">{papers.length}</div>
            <div className="repo-stat-lbl">Indexed Documents</div>
          </div>
        </div>

        <div className="repo-stat-card glass-panel">
          <div className="repo-stat-icon-wrap bg-cyan-subtle">
            <FileText size={22} className="text-cyan" />
          </div>
          <div>
            <div className="repo-stat-val font-mono">{totalPages}</div>
            <div className="repo-stat-lbl">Total Pages Parsed</div>
          </div>
        </div>

        <div className="repo-stat-card glass-panel">
          <div className="repo-stat-icon-wrap bg-purple-subtle">
            <Layers size={22} className="text-purple" />
          </div>
          <div>
            <div className="repo-stat-val font-mono">{totalChunks}</div>
            <div className="repo-stat-lbl">FAISS Vector Chunks</div>
          </div>
        </div>

        <div className="repo-stat-card glass-panel">
          <div className="repo-stat-icon-wrap bg-emerald-subtle">
            <HardDrive size={22} className="text-emerald" />
          </div>
          <div>
            <div className="repo-stat-val font-mono">{formatBytes(totalSize)}</div>
            <div className="repo-stat-lbl">Storage Occupied</div>
          </div>
        </div>
      </div>

      {deleteSuccess && (
        <div className="success-banner glass-panel">
          <CheckCircle size={18} className="text-emerald" />
          <span>{deleteSuccess}</span>
        </div>
      )}

      {deleteError && (
        <div className="error-banner glass-panel">
          <AlertCircle size={18} className="text-rose" />
          <span>{deleteError}</span>
        </div>
      )}

      <div className="repo-sector-filters" aria-label="Filter papers by category">
        <button
          type="button"
          className={`repo-sector-chip ${categoryFilter === 'All' ? 'active' : ''}`}
          onClick={() => setCategoryFilter?.('All')}
        >
          All <span>{papers.length}</span>
        </button>
        {sectorOptions.map((sector) => {
          const count = papers.filter((paper) => (paper.category || paper.sector || 'Other') === sector).length;
          return (
            <button
              key={sector}
              type="button"
              className={`repo-sector-chip ${categoryFilter === sector ? 'active' : ''}`}
              onClick={() => setCategoryFilter?.(sector)}
            >
              {sector} <span>{count}</span>
            </button>
          );
        })}
      </div>

      <div className="repo-sector-groups">
        {papersBySector.map(({ sector, papers: sectorPapers }) => (
          <section key={sector} className="repo-sector-group">
            <button
              type="button"
              className="repo-sector-heading"
              aria-expanded={!collapsedSectors[sector]}
              onClick={() => toggleSector(sector)}
            >
              <span>{sector} ({sectorPapers.length})</span>
              <span className="repo-sector-chevron">{collapsedSectors[sector] ? '+' : '−'}</span>
            </button>
            {!collapsedSectors[sector] && (
              <div className="papers-table-container glass-panel">
                <table className="papers-table">
                  <colgroup>
                    <col className="paper-title-column" />
                    <col className="paper-pages-column" />
                    <col className="paper-chunks-column" />
                    <col className="paper-sector-column" />
                    <col className="paper-size-column" />
                    <col className="paper-status-column" />
                    <col className="paper-actions-column" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Paper Title &amp; Filename</th>
                      <th>Pages</th>
                      <th>FAISS Chunks</th>
                      <th>Category</th>
                      <th>File Size</th>
                      <th>Storage Status</th>
                      <th className="text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sectorPapers.map((p) => (
                      <tr key={p.name} className="paper-table-row">
                        <td className="paper-name-col">
                          <div className="paper-icon-name">
                            <FileText size={18} className="text-indigo shrink-0" />
                            <div className="paper-name-details">
                              <div className="paper-name-text" title={p.name}>
                                {p.name}
                              </div>
                              <div className="paper-path-sub font-mono" title={`research_papers/${p.name}`}>
                                research_papers/{p.name}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="font-mono text-cyan font-semibold">{p.pages} pp</td>
                        <td className="font-mono text-highlight paper-chunks-cell">{p.chunks} chunks</td>
                        <td>
                          <select
                            className="select-control repo-sector-select"
                            aria-label={`Sector for ${p.name}`}
                            value={p.category || p.sector || 'Other'}
                            onChange={(event) => handleSectorChange(p.name, event.target.value)}
                            disabled={updatingSectorName === p.name}
                          >
                            {sectorOptions.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                            <option value="__create_new__">Create new category...</option>
                          </select>
                        </td>
                        <td className="font-mono text-muted">{formatBytes(p.file_size)}</td>
                        <td>
                          <span className={`badge ${p.file_exists ? 'badge-success' : 'badge-amber'}`}>
                            {p.file_exists ? 'Indexed' : 'Missing'}
                          </span>
                        </td>
                        <td className="text-right">
                          <div className="paper-actions-group">
                            <a
                              href={api.getPaperFileUrl(p.name)}
                              target="_blank"
                              rel="noreferrer"
                              className="btn btn-outline btn-sm"
                              title="Open PDF in new tab"
                            >
                              <ExternalLink size={13} />
                              <span>View PDF</span>
                            </a>

                            <button
                              className="btn btn-secondary btn-sm"
                              title="Run automated 14-dimension analysis"
                              onClick={() => onSelectPaperForAnalysis(p.name)}
                            >
                              <FileSearch size={13} />
                              <span>Analyze</span>
                            </button>

                            <button
                              className="btn btn-danger btn-sm"
                              title="Remove paper from FAISS index and delete file"
                              onClick={() => handleDelete(p.name)}
                              disabled={deletingName === p.name}
                            >
                              <Trash2 size={13} />
                              <span>{deletingName === p.name ? 'Deleting...' : 'Delete'}</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ))}
        {papersBySector.length === 0 && (
          <div className="empty-placeholder-card glass-panel">
            <Library size={36} className="text-muted" />
            <p>No papers in this sector.</p>
          </div>
        )}
      </div>
    </div>
  );
}
