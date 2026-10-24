/**
 * AI Research Copilot - Frontend API Client
 * Connects to the FastAPI backend running on port 8000 (proxied via /api or direct fallback)
 */

const API_BASE = '/api';

export const api = {
  // System Health
  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Health check failed (${res.status})`);
    return res.json();
  },

  // Papers Management
  async getPapers() {
    const res = await fetch(`${API_BASE}/papers`);
    if (!res.ok) throw new Error(`Failed to load papers (${res.status})`);
    return res.json();
  },

  async uploadPaper(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  async deletePaper(paperName, deleteFile = true) {
    const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperName)}?delete_file=${deleteFile}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Deletion failed' }));
      throw new Error(err.detail || 'Deletion failed');
    }
    return res.json();
  },

  async updatePaperCategory(paperName, category) {
    const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperName)}/category`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update paper sector' }));
      throw new Error(err.detail || 'Failed to update paper sector');
    }
    return res.json();
  },

  getPaperFileUrl(paperName) {
    return `${API_BASE}/paper-file/${encodeURIComponent(paperName)}`;
  },

  // Semantic Vector Search
  async search(query, topK = 5, paperFilter = null, scoreThreshold = 0.0, categoryFilter = null) {
    const res = await fetch(`${API_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        top_k: topK,
        paper_filter: paperFilter && paperFilter.length > 0 ? paperFilter : null,
        score_threshold: scoreThreshold,
        category_filter: categoryFilter && categoryFilter.length > 0 ? categoryFilter : null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Search failed' }));
      throw new Error(err.detail || 'Search failed');
    }
    return res.json();
  },

  // RAG Question Answering
  async ask(question, topK = 6, paperFilter = null, saveReport = false, categoryFilter = null) {
    const res = await fetch(`${API_BASE}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        top_k: topK,
        paper_filter: paperFilter && paperFilter.length > 0 ? paperFilter : null,
        category_filter: categoryFilter && categoryFilter.length > 0 ? categoryFilter : null,
        save_report: saveReport,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ask request failed' }));
      throw new Error(err.detail || 'Ask request failed');
    }
    return res.json();
  },

  // Deep Paper Analysis
  async analyzePaper(paperId, saveReport = false) {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_id: paperId,
        save_report: saveReport,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Analysis failed' }));
      throw new Error(err.detail || 'Analysis failed');
    }
    return res.json();
  },

  async regenerateArchitecture(paperId, invalidMermaid) {
    const res = await fetch(`${API_BASE}/analysis/architecture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_id: paperId, invalid_mermaid: invalidMermaid }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Architecture retry failed' }));
      throw new Error(err.detail || 'Architecture retry failed');
    }
    return res.json();
  },

  async downloadAnalysisPdf(report) {
    const res = await fetch(`${API_BASE}/analysis/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'PDF report download failed' }));
      throw new Error(err.detail || 'PDF report download failed');
    }
    return res.blob();
  },

  // Multi-Paper Comparison
  async comparePapers(paperNames, saveReport = false) {
    const res = await fetch(`${API_BASE}/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_names: paperNames,
        save_report: saveReport,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Comparison failed' }));
      throw new Error(err.detail || 'Comparison failed');
    }
    return res.json();
  },

  // Research Gap Detection
  async detectResearchGaps(paperId, saveReport = false) {
    const res = await fetch(`${API_BASE}/research-gap`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_id: paperId,
        save_report: saveReport,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Research gap analysis failed' }));
      throw new Error(err.detail || 'Research gap analysis failed');
    }
    return res.json();
  },

  // Generated Outputs
  async getOutputs() {
    const res = await fetch(`${API_BASE}/outputs`);
    if (!res.ok) throw new Error(`Failed to load outputs (${res.status})`);
    return res.json();
  },
};
