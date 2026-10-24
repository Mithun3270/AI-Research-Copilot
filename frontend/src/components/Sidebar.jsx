import React from 'react';
import {
  MessageSquareText,
  FileSearch,
  Scale,
  Sparkles,
  Library,
  Layers,
} from 'lucide-react';

export default function Sidebar({
  currentTab,
  setTab,
  papersCount,
  categories = [],
  onSelectCategory,
  selectedCategory = 'All',
  outputsCount,
}) {
  const navItems = [
    {
      id: 'chat',
      label: 'Research Chat',
      icon: MessageSquareText,
      badge: 'RAG',
      badgeClass: 'badge-primary',
    },
    {
      id: 'analysis',
      label: 'Paper Analysis',
      icon: FileSearch,
      badge: '14-pt',
      badgeClass: 'badge-cyan',
    },
    {
      id: 'compare',
      label: 'Paper Comparator',
      icon: Scale,
      badge: 'Matrix',
      badgeClass: 'badge-purple',
    },
    {
      id: 'gaps',
      label: 'Research Gaps',
      icon: Sparkles,
      badge: 'AI Ideas',
      badgeClass: 'badge-amber',
    },
    {
      id: 'papers',
      label: 'Paper Repository',
      icon: Library,
      badge: `${papersCount} PDFs`,
      badgeClass: 'badge-cyan',
    },
  ];

  return (
    <aside className="app-sidebar">
      <div className="sidebar-section-title">RESEARCH WORKBENCH</div>
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              id={`nav-tab-${item.id}`}
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              <div className="nav-item-content">
                <Icon size={18} className="nav-icon" />
                <span className="nav-label">{item.label}</span>
              </div>
              {item.badge && (
                <span className={`badge ${item.badgeClass}`}>{item.badge}</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-categories">
        <div className="sidebar-section-title">PAPER CATEGORIES</div>
        {categories.map((category) => (
          <button
            key={category.name}
            type="button"
            className={`sidebar-category-button ${selectedCategory === category.name ? 'active' : ''}`}
            title={`${category.name} (${category.paper_count} papers)`}
            onClick={() => onSelectCategory?.(category.name)}
          >
            <span className="sidebar-category-name">{category.name}</span>
            <span className="sidebar-category-count">{category.paper_count}</span>
          </button>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="corpus-summary-card glass-panel">
          <div className="corpus-title">
            <Layers size={15} className="text-indigo" />
            <span>Active Knowledge Base</span>
          </div>
          <div className="corpus-stats">
            <div className="stat-item">
              <span className="stat-label">Indexed Papers</span>
              <span className="stat-value">{papersCount}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Engine</span>
              <span className="stat-value">FAISS FlatIP</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
