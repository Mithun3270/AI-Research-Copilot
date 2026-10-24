import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatView from './components/ChatView';
import AnalysisView from './components/AnalysisView';
import ComparisonView from './components/ComparisonView';
import ResearchGapsView from './components/ResearchGapsView';
import PapersView from './components/PapersView';
import UploadModal from './components/UploadModal';
import { api } from './services/api';
import './App.css';

const comparisonStorageKey = 'ai-research-copilot-comparison';

const getInitialComparisonState = () => {
  try {
    const stored = sessionStorage.getItem(comparisonStorageKey);
    const parsed = stored ? JSON.parse(stored) : null;
    return parsed && Array.isArray(parsed.selectedPapers)
      ? {
        selectedPapers: parsed.selectedPapers,
        comparisonResult: parsed.comparisonResult || null,
      }
      : { selectedPapers: [], comparisonResult: null };
  } catch {
    return { selectedPapers: [], comparisonResult: null };
  }
};

export default function App() {
  const [currentTab, setCurrentTab] = useState('chat');
  const [health, setHealth] = useState(null);
  const [papers, setPapers] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [categories, setCategories] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [selectedAnalysisPaper, setSelectedAnalysisPaper] = useState(null);
  const [selectedChatPaper, setSelectedChatPaper] = useState(null);
  const [comparisonState, setComparisonState] = useState(getInitialComparisonState);

  useEffect(() => {
    sessionStorage.setItem(comparisonStorageKey, JSON.stringify(comparisonState));
  }, [comparisonState]);

  const fetchSystemData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, papersData] = await Promise.all([
        api.getHealth().catch((e) => ({ status: 'error', error: e.message })),
        api.getPapers().catch(() => ({ count: 0, papers: [] })),
      ]);
      setHealth(healthData);
      setPapers(papersData.papers || []);
      setSectors(papersData.sectors || []);
      setCategories(papersData.categories || (papersData.sectors || []).map((name) => ({ name, paper_count: 0 })));
    } catch (err) {
      setError(err.message || 'Unable to connect to backend engine.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSystemData();
  }, []);

  const handleSelectPaperForAnalysis = (paperName) => {
    setSelectedAnalysisPaper(paperName);
    setCurrentTab('analysis');
  };

  const handleAskFollowUpInChat = (paperName) => {
    setSelectedChatPaper(paperName);
    setCurrentTab('chat');
  };

  const handleComparisonPaperDeleted = (paperName) => {
    setComparisonState((current) => (
      current.selectedPapers.includes(paperName)
        ? { selectedPapers: [], comparisonResult: null }
        : current
    ));
  };

  return (
    <div className="app-root">
      <Header
        health={health}
        papersCount={papers.length}
        onOpenUpload={() => setUploadModalOpen(true)}
        onRefresh={fetchSystemData}
        loading={loading}
      />

      <div className="app-body">
        <Sidebar
          currentTab={currentTab}
          setTab={setCurrentTab}
          papersCount={papers.length}
          categories={categories}
          selectedCategory={categoryFilter}
          onSelectCategory={(category) => {
            setCategoryFilter(category);
            setCurrentTab('papers');
          }}
        />

        <main className="main-viewport">
          {currentTab === 'chat' && (
            <ChatView
              papers={papers}
              categories={categories}
              initialPaper={selectedChatPaper}
              onInitialPaperApplied={() => setSelectedChatPaper(null)}
            />
          )}

          {currentTab === 'analysis' && (
            <AnalysisView
              papers={papers}
              initialPaper={selectedAnalysisPaper}
              onAskInChat={handleAskFollowUpInChat}
            />
          )}

          {currentTab === 'compare' && (
            <ComparisonView
              papers={papers}
              selectedPapers={comparisonState.selectedPapers}
              comparisonResult={comparisonState.comparisonResult}
              setComparisonState={setComparisonState}
            />
          )}

          {currentTab === 'gaps' && (
            <ResearchGapsView papers={papers} />
          )}

          {currentTab === 'papers' && (
            <PapersView
              papers={papers}
              sectors={sectors}
              categoryFilter={categoryFilter}
              setCategoryFilter={setCategoryFilter}
              onSelectPaperForAnalysis={handleSelectPaperForAnalysis}
              onRefresh={fetchSystemData}
              onPaperDeleted={handleComparisonPaperDeleted}
            />
          )}
        </main>
      </div>

      <UploadModal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onUploadSuccess={() => {
          fetchSystemData();
        }}
      />
    </div>
  );
}
