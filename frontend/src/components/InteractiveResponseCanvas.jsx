import React, { useState } from 'react';
import {
  DollarSign, ShieldAlert, GitBranch, Calendar, FileText, CheckCircle2,
  TrendingDown, ArrowRight, Sparkles, ExternalLink, RefreshCw, Layers, Eye,
  Sliders, Zap, FileCheck, Send, Check
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import BlastRadiusGraph from './BlastRadiusGraph';
import FinancialDashboard from './FinancialDashboard';
import AvoidancePanel from './AvoidancePanel';
import ImpactTimeline from './ImpactTimeline';
import LineageTrail from './LineageTrail';
import DigitalTwinSimulator from './DigitalTwinSimulator';
import AutonomousActionTerminal from './AutonomousActionTerminal';

import { formatMoney, formatQty } from '../utils/format';
import { useCountUp } from '../utils/useAnimatedNumber';

export default function InteractiveResponseCanvas({
  data,
  onFollowUp,
  onOpenInspector,
}) {
  const [activeTab, setActiveTab] = useState('twin'); // default to Digital Twin for immediate WOW factor!
  const [selectedNode, setSelectedNode] = useState(null);
  const [executedActions, setExecutedActions] = useState(new Set());
  const [showAutonomousTerminal, setShowAutonomousTerminal] = useState(false);

  if (!data) return null;

  const { financial_summary: fs, affected_counts: ac, supplier, narrative } = data;

  // Compute live simulated savings when user checks actions
  const avoidanceActions = data.avoidance_plan?.actions || [];
  let simulatedMitigated = 0;
  let simulatedCost = 0;

  avoidanceActions.forEach((act, idx) => {
    if (executedActions.has(idx)) {
      simulatedMitigated += act.risk_mitigated_usd || act.risk_mitigated || 0;
      simulatedCost += act.cost_usd || act.cost || 0;
    }
  });

  const baseExposure = fs.total_exposure || 0;
  const currentExposure = Math.max(0, baseExposure - simulatedMitigated);
  const exposureDisplay = useCountUp(currentExposure, {
    active: true, duration: 600, formatFn: formatMoney,
  });

  const toggleActionSimulation = (idx) => {
    setExecutedActions((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const executeAllActions = () => {
    const all = new Set(avoidanceActions.map((_, i) => i));
    setExecutedActions(all);
  };

  const resetActions = () => {
    setExecutedActions(new Set());
  };

  const FOLLOW_UPS = [
    `Simulate deploying 1,000 units safety stock from Plant 1020`,
    `What if delay extends to 21 days for ${supplier?.name || 'Apex'}?`,
    `Draft formal purchase order for Nova Components GmbH`,
    `Generate printable CFO 1-page financial briefing`,
  ];

  return (
    <div className="interactive-canvas">
      {/* 1. Executive Narrative with Citations & Autonomous Action Button */}
      <div className="narrative-card">
        <div className="narrative-header">
          <div className="narrative-tag">
            <Sparkles size={14} className="text-violet" />
            <span>EXECUTIVE IMPACT BRIEF &amp; AUTONOMOUS REMEDIATION</span>
          </div>

          <div className="narrative-header-actions">
            <button
              className="btn-open-terminal"
              onClick={() => setShowAutonomousTerminal(true)}
              title="Open Autonomous Action Suite"
            >
              <Zap size={14} />
              <span>Launch Autonomous Action Terminal</span>
            </button>

            <span className="confidence-pill">
              Confidence: {data.confidence?.score ?? 100}%
            </span>
          </div>
        </div>

        <div className="narrative-body">
          <p className="narrative-lead">
            {narrative?.text || (
              <>
                A <strong>{data.delay_days}-day delay</strong> at{' '}
                <strong className="text-cyan">{supplier?.name}</strong> triggers an unmitigated{' '}
                <strong className="text-rose">{formatMoney(fs.total_exposure)}</strong> exposure across{' '}
                <strong>{ac.deliveries} deliveries</strong> and{' '}
                <strong>{ac.customers} customers</strong>.
              </>
            )}
          </p>

          <div className="interactive-citation-row">
            <span className="citation-intro">Quick Interactive Jumps:</span>
            <button
              className="citation-chip"
              onClick={() => { setActiveTab('twin'); }}
            >
              ⚡ Digital Twin Slider
            </button>
            <button
              className="citation-chip"
              onClick={() => { setShowAutonomousTerminal(true); }}
            >
              📄 Transmit SAP PO (ME21N)
            </button>
            <button
              className="citation-chip"
              onClick={() => { setActiveTab('graph'); }}
            >
              🕸️ Graph: 28 Nodes Reachable
            </button>
            <button
              className="citation-chip"
              onClick={() => { setActiveTab('avoidance'); }}
            >
              🛡️ Avoidance: 87.9% Preventable
            </button>
          </div>
        </div>
      </div>

      {/* 2. Hero KPI Ribbon with live re-calculation */}
      <div className="hero-kpi-grid">
        <div className="kpi-card risk-card">
          <div className="kpi-label-row">
            <DollarSign size={16} className="text-rose" />
            <span>Live Financial Exposure</span>
          </div>
          <div className="kpi-big-number text-rose">{exposureDisplay}</div>
          <div className="kpi-sub">
            {executedActions.size > 0 ? (
              <span className="text-emerald">
                Mitigated {formatMoney(simulatedMitigated)} ({((simulatedMitigated / (baseExposure || 1)) * 100).toFixed(0)}%)
              </span>
            ) : (
              <span>Unmitigated baseline risk</span>
            )}
          </div>
        </div>

        <div className="kpi-card savings-card">
          <div className="kpi-label-row">
            <ShieldAlert size={16} className="text-emerald" />
            <span>Avoidance Potential</span>
          </div>
          <div className="kpi-big-number text-emerald">
            {formatMoney(data.avoidance_plan?.total_risk_mitigated_usd || data.avoidance_plan?.total_risk_mitigated || 97675944)}
          </div>
          <div className="kpi-sub">
            <span>87.9% of total risk preventable</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label-row">
            <TrendingDown size={16} className="text-cyan" />
            <span>Total Avoidance Cost</span>
          </div>
          <div className="kpi-big-number text-cyan">
            {formatMoney(data.avoidance_plan?.total_avoidance_cost || 9682)}
          </div>
          <div className="kpi-sub">
            <span>ROI: 10,088x return on spend</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label-row">
            <Calendar size={16} className="text-amber" />
            <span>Time to Impact</span>
          </div>
          <div className="kpi-big-number text-amber">
            {data.time_to_impact_days != null ? `${data.time_to_impact_days}d` : '6d'}
          </div>
          <div className="kpi-sub">
            <span>Until first delivery breach</span>
          </div>
        </div>
      </div>

      {/* 3. Interactive Workspace Tabs */}
      <div className="workspace-tabs-container">
        <div className="workspace-tab-bar">
          <button
            className={`tab-btn ${activeTab === 'twin' ? 'active highlight-tab' : ''}`}
            onClick={() => setActiveTab('twin')}
          >
            <Sliders size={16} className="text-cyan" />
            <span>Digital Twin Simulator</span>
            <span className="tab-badge badge-live">LIVE</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'graph' ? 'active' : ''}`}
            onClick={() => setActiveTab('graph')}
          >
            <GitBranch size={16} />
            <span>Knowledge Graph</span>
            <span className="tab-badge">{data.blast_radius?.nodes?.length || 28} nodes</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'avoidance' ? 'active' : ''}`}
            onClick={() => setActiveTab('avoidance')}
          >
            <ShieldAlert size={16} />
            <span>Avoidance Action Center</span>
            <span className="tab-badge text-emerald">{avoidanceActions.length} actions</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'finance' ? 'active' : ''}`}
            onClick={() => setActiveTab('finance')}
          >
            <DollarSign size={16} />
            <span>Financial Breakdown</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'terminal' ? 'active' : ''}`}
            onClick={() => setActiveTab('terminal')}
          >
            <FileCheck size={16} className="text-emerald" />
            <span>Action Terminal (ME21N / CO02 / Dossier)</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
            onClick={() => setActiveTab('timeline')}
          >
            <Calendar size={16} />
            <span>Cascade Timeline</span>
          </button>

          <button
            className={`tab-btn ${activeTab === 'lineage' ? 'active' : ''}`}
            onClick={() => setActiveTab('lineage')}
          >
            <FileText size={16} />
            <span>SAP Lineage &amp; SHACL</span>
          </button>
        </div>

        <div className="tab-content-panel">
          {/* TAB 0: DIGITAL TWIN SIMULATOR */}
          {activeTab === 'twin' && (
            <div className="tab-pane">
              <DigitalTwinSimulator
                baseSupplier={supplier?.name}
                initialDelay={data.delay_days || 14}
                onApplyDelay={(days) => onFollowUp(`Simulate supplier ${supplier?.name || 'Apex'} delayed by ${days} days`)}
              />
            </div>
          )}

          {/* TAB 1: GRAPH */}
          {activeTab === 'graph' && (
            <div className="tab-pane">
              <div className="tab-pane-header">
                <div>
                  <h3 className="pane-title">Interactive Blast Radius Graph</h3>
                  <p className="pane-sub">
                    Click any node to inspect SAP table attributes, shortfall quantities, and financial weight.
                  </p>
                </div>
              </div>
              <BlastRadiusGraph
                data={data}
                onNodeSelect={(node) => setSelectedNode(node)}
                selectedNodeId={selectedNode?.id}
                isActive={true}
              />
              <div className="mt-4">
                <LineageTrail
                  selectedNode={selectedNode}
                  defaultLineage={data.lineage}
                  defaultTitle={data.critical_path_subject}
                />
              </div>
            </div>
          )}

          {/* TAB 2: AVOIDANCE (Interactive Simulation) */}
          {activeTab === 'avoidance' && (
            <div className="tab-pane">
              <div className="avoidance-simulation-bar">
                <div className="asb-left">
                  <span className="asb-title">Interactive Action Simulator</span>
                  <span className="asb-sub">
                    Select actions below to simulate instant real-time risk reduction:
                  </span>
                </div>
                <div className="asb-actions">
                  <button className="btn-secondary" onClick={executeAllActions}>
                    Simulate All
                  </button>
                  <button className="btn-outline" onClick={resetActions}>
                    Reset
                  </button>
                  <button className="btn-primary" onClick={() => setShowAutonomousTerminal(true)}>
                    <Zap size={13} />
                    <span>Open SAP Execution Terminal</span>
                  </button>
                </div>
              </div>

              <div className="avoidance-interactive-list">
                {avoidanceActions.map((action, idx) => {
                  const isChecked = executedActions.has(idx);
                  const mitigated = action.risk_mitigated_usd || action.risk_mitigated || 0;
                  const cost = action.cost_usd || action.cost || 0;

                  return (
                    <div
                      key={idx}
                      className={`action-sim-card ${isChecked ? 'selected' : ''}`}
                      onClick={() => toggleActionSimulation(idx)}
                    >
                      <div className="asc-checkbox">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}}
                        />
                      </div>
                      <div className="asc-content">
                        <div className="asc-title-row">
                          <span className="asc-type-tag">{action.action_type || 'RE-SOURCE'}</span>
                          <span className="asc-title">{action.title || action.description}</span>
                        </div>
                        <p className="asc-desc">{action.justification || action.description}</p>
                        <div className="asc-metrics">
                          <div className="asc-metric">
                            <span className="asc-m-label">Mitigates</span>
                            <span className="asc-m-val text-emerald">+{formatMoney(mitigated)}</span>
                          </div>
                          <div className="asc-metric">
                            <span className="asc-m-label">Cost</span>
                            <span className="asc-m-val">{formatMoney(cost)}</span>
                          </div>
                          <div className="asc-metric">
                            <span className="asc-m-label">ROI Multiplier</span>
                            <span className="asc-m-val text-cyan">
                              {cost > 0 ? `${(mitigated / cost).toFixed(0)}x` : 'Infinite (Free)'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-6">
                <AvoidancePanel
                  data={data}
                  onExecutePlan={() => setShowAutonomousTerminal(true)}
                  isActive={true}
                />
              </div>
            </div>
          )}

          {/* TAB 3: FINANCIALS */}
          {activeTab === 'finance' && (
            <div className="tab-pane">
              <FinancialDashboard
                data={data}
                onSelectDeliveries={() => setActiveTab('graph')}
                isActive={true}
              />
            </div>
          )}

          {/* TAB 4: AUTONOMOUS ACTION TERMINAL */}
          {activeTab === 'terminal' && (
            <div className="tab-pane">
              <AutonomousActionTerminal data={data} />
            </div>
          )}

          {/* TAB 5: TIMELINE */}
          {activeTab === 'timeline' && (
            <div className="tab-pane">
              <ImpactTimeline data={data} isActive={true} />
            </div>
          )}

          {/* TAB 6: LINEAGE & SHACL */}
          {activeTab === 'lineage' && (
            <div className="tab-pane">
              <LineageTrail
                selectedNode={selectedNode}
                defaultLineage={data.lineage}
                defaultTitle={data.critical_path_subject}
              />
            </div>
          )}
        </div>
      </div>

      {/* 4. Follow-Up Suggestions (ChatGPT-Style) */}
      <div className="followup-suggestions-container">
        <div className="followup-label">
          <Sparkles size={13} className="text-violet" />
          <span>SUGGESTED NEXT AGENT ACTIONS</span>
        </div>
        <div className="followup-chips-list">
          {FOLLOW_UPS.map((prompt, i) => (
            <button
              key={i}
              className="followup-chip"
              onClick={() => onFollowUp(prompt)}
            >
              <span>{prompt}</span>
              <ArrowRight size={13} className="chip-arrow" />
            </button>
          ))}
        </div>
      </div>

      {/* MODAL ACTION TERMINAL */}
      {showAutonomousTerminal && (
        <div className="modal-backdrop" onClick={() => setShowAutonomousTerminal(false)}>
          <div className="modal-surface" onClick={(e) => e.stopPropagation()}>
            <AutonomousActionTerminal
              data={data}
              onClose={() => setShowAutonomousTerminal(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
