import React from 'react';
import {
  Menu, Cpu, Database, ShieldCheck, Sparkles, RefreshCw, FileText, ExternalLink
} from 'lucide-react';

export default function ChatHeader({
  sidebarOpen,
  onToggleSidebar,
  currentScenario,
  onReset,
  onOpenInspector,
  systemHealth,
}) {
  return (
    <header className="chat-header">
      <div className="header-left">
        {!sidebarOpen && (
          <button className="header-icon-btn" onClick={onToggleSidebar} title="Open sidebar">
            <Menu size={18} />
          </button>
        )}
        <div className="model-selector-badge">
          <div className="model-badge-icon">
            <Sparkles size={14} className="text-violet" />
          </div>
          <div className="model-badge-info">
            <span className="model-name">
              {systemHealth?.llm?.model ? `Azure AI · ${systemHealth.llm.model}` : 'DeepSeek-V4-Pro'}
            </span>
            <span className="model-sub">SAP Neurosymbolic Engine</span>
          </div>
        </div>
      </div>

      <div className="header-center">
        {currentScenario?.title && (
          <div className="scenario-pill">
            <span className="scenario-dot" />
            <span className="scenario-text">{currentScenario.title}</span>
          </div>
        )}
      </div>

      <div className="header-right">
        <button className="header-pill-btn" onClick={onOpenInspector} title="Inspect SAP Tables">
          <Database size={14} />
          <span>DDIC Catalog</span>
        </button>
        <button className="header-pill-btn reset-btn" onClick={onReset} title="Start new simulation">
          <RefreshCw size={14} />
          <span>New Prompt</span>
        </button>
      </div>
    </header>
  );
}
