import React from 'react';
import {
  Plus, MessageSquare, ShieldCheck, Database, Cpu, Sparkles,
  ChevronLeft, ChevronRight, Trash2, Zap, AlertTriangle, Layers
} from 'lucide-react';

export default function ChatSidebar({
  isOpen,
  onToggle,
  scenarios = [],
  activeScenarioId,
  onSelectScenario,
  onNewScenario,
  onClearScenarios,
  onSelectPreset,
  systemHealth,
  onOpenInspector,
}) {
  const PRESET_DEMOS = [
    {
      id: 'apex-14',
      title: 'Apex Microelectronics (+14d)',
      subtitle: '$111.2M cascade across 5 customers',
      badge: '$111.2M',
      risk: 'critical',
      query: 'Supplier Apex Microelectronics is delayed by 14 days. What is our financial risk and how do we avoid it?',
    },
    {
      id: 'mcu32-sole',
      title: 'MCU-32 Sole-Source Risk',
      subtitle: 'Single point of failure stress test',
      badge: 'Sole-Source',
      risk: 'high',
      query: 'What if we lose our sole source for MCU-32 microcontrollers for 21 days?',
    },
    {
      id: 'plant-downtime',
      title: 'Plant 1010 Downtime (+7d)',
      subtitle: 'Cross-plant inventory cascade',
      badge: '$42.5M',
      risk: 'medium',
      query: 'Show me all customers affected if Plant 1010 goes offline for 7 days.',
    },
    {
      id: 'toshiro-safe',
      title: 'Toshiro Metals (+7d)',
      subtitle: 'Buffer absorbs delay (zero loss)',
      badge: '$0 Loss',
      risk: 'safe',
      query: 'How exposed are we if Toshiro Metals is 7 days late?',
    },
  ];

  return (
    <aside className={`chat-sidebar ${isOpen ? 'open' : 'collapsed'}`}>
      <div className="sidebar-top">
        <button className="new-chat-btn" onClick={onNewScenario} title="Start New Simulation">
          <Plus size={18} className="icon-spin-hover" />
          {isOpen && <span>New Simulation</span>}
        </button>
        <button className="collapse-toggle-btn" onClick={onToggle} title={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}>
          {isOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
        </button>
      </div>

      {isOpen && (
        <div className="sidebar-content">
          {/* Pinned Presets for Demos */}
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <Zap size={13} className="text-amber" />
              <span>DEMO SCENARIOS</span>
            </div>
            <div className="sidebar-list">
              {PRESET_DEMOS.map((preset) => (
                <button
                  key={preset.id}
                  className={`sidebar-item preset-item ${activeScenarioId === preset.id ? 'active' : ''}`}
                  onClick={() => onSelectPreset(preset)}
                >
                  <div className="item-icon-box">
                    <Sparkles size={14} />
                  </div>
                  <div className="item-meta">
                    <div className="item-title-row">
                      <span className="item-title">{preset.title}</span>
                      <span className={`risk-pill ${preset.risk}`}>{preset.badge}</span>
                    </div>
                    <span className="item-sub">{preset.subtitle}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* History of run queries */}
          <div className="sidebar-section flex-1">
            <div className="sidebar-section-header">
              <MessageSquare size={13} />
              <span>SIMULATION HISTORY</span>
              {scenarios.length > 0 && (
                <button
                  className="clear-history-btn"
                  onClick={onClearScenarios}
                  title="Clear all history"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
            <div className="sidebar-list history-list">
              {scenarios.length === 0 ? (
                <div className="empty-history">
                  <span>No simulations yet</span>
                  <span className="text-xs text-muted">Run a scenario to save history</span>
                </div>
              ) : (
                scenarios.map((sc) => (
                  <button
                    key={sc.id}
                    className={`sidebar-item ${activeScenarioId === sc.id ? 'active' : ''}`}
                    onClick={() => onSelectScenario(sc.id)}
                  >
                    <div className="item-icon-box">
                      <Layers size={14} />
                    </div>
                    <div className="item-meta">
                      <div className="item-title-row">
                        <span className="item-title truncate">{sc.title || sc.query}</span>
                        {sc.exposure && (
                          <span className="risk-pill critical">{sc.exposure}</span>
                        )}
                      </div>
                      <span className="item-sub">{sc.timestamp}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* System Status & Governance Footer */}
          <div className="sidebar-footer">
            <div className="status-card">
              <div className="status-row">
                <div className="status-label">
                  <span className="status-dot online" />
                  <Cpu size={13} />
                  <span>LLM Agent</span>
                </div>
                <span className="status-value text-emerald">
                  {systemHealth?.llm?.model || 'DeepSeek-V4-Pro'}
                </span>
              </div>
              <div className="status-row">
                <div className="status-label">
                  <span className="status-dot online" />
                  <Database size={13} />
                  <span>Graph Core</span>
                </div>
                <span className="status-value">
                  {systemHealth?.graph?.backend === 'neo4j' ? 'Neo4j Aura' : 'In-Memory (275)'}
                </span>
              </div>
              <div className="status-row">
                <div className="status-label">
                  <span className="status-dot online" />
                  <ShieldCheck size={13} />
                  <span>SHACL</span>
                </div>
                <span className="status-value text-emerald">100% Conforms</span>
              </div>
            </div>

            <button className="inspector-trigger-btn" onClick={onOpenInspector}>
              <Database size={14} />
              <span>Explore SAP DDIC Catalog</span>
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
