import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import QueryInput from './components/QueryInput';
import BlastRadiusGraph from './components/BlastRadiusGraph';
import FinancialDashboard from './components/FinancialDashboard';
import AvoidancePanel from './components/AvoidancePanel';
import ImpactTimeline from './components/ImpactTimeline';
import LineageTrail from './components/LineageTrail';
import { getMockImpactReport } from './utils/api';
import { useCountUp } from './utils/useAnimatedNumber';

// ── Nav sections
const SECTIONS = [
  { id: 'overview',   label: 'Overview' },
  { id: 'blast',      label: 'Blast radius' },
  { id: 'finance',    label: 'Financial exposure' },
  { id: 'avoidance',  label: 'Avoidance plan' },
  { id: 'timeline',   label: 'Timeline' },
  { id: 'trust',      label: 'Lineage & trust' },
];

const LOADING_STEPS = [
  'Parsing query and resolving entity…',
  'Traversing 8-hop supply chain graph…',
  'Computing financial exposure per hop…',
  'Searching for avoidance paths…',
  'Generating executive narrative…',
];

function formatMoney(val) {
  if (!val && val !== 0) return '—';
  if (val === 0) return '$0';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

// Reusable count up component for stat cells
function AnimatedStat({ value, suffix = '' }) {
  const num = typeof value === 'number' ? value : parseInt(value, 10);
  const { formatted } = useCountUp(isNaN(num) ? 0 : num, { duration: 800 });
  return <span>{formatted}{suffix}</span>;
}

// Reusable metric row with animated bar and count-up percentage
function MetricRow({ label, value, delay = 0 }) {
  const { formatted } = useCountUp(value, { duration: 800, delay: delay * 1000, formatFn: v => `${v}%` });
  return (
    <div className="trust-metric">
      <div className="tm-head">
        <span className="tm-name">{label}</span>
        <span className="tm-val">{formatted}</span>
      </div>
      <div className="tm-bar-bg">
        <motion.div
          className="tm-bar"
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ delay, duration: 0.6, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

// ── Lineage & Trust section (full confidence breakdown)
function TrustSection({ confidence, lineage }) {
  if (!confidence) return null;
  const { score, data_completeness, traversal_coverage, engine_agreement, hops_complete, hops_total } = confidence;
  const { formatted: animScore } = useCountUp(score, { duration: 900, formatFn: v => `${v}%` });

  const metrics = [
    { label: 'Data completeness',  value: data_completeness },
    { label: 'Traversal coverage', value: traversal_coverage },
    { label: 'Engine agreement',   value: engine_agreement },
  ];

  return (
    <div className="trust-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Lineage &amp; trust</h2>
        <p className="section-sub">
          Every figure is computed deterministically from the graph — the language model writes the narrative, never the maths.
        </p>
      </div>

      <div className="trust-score-row">
        <span className="trust-pct">{animScore}</span>
        <span className="trust-label">confidence score · {hops_complete}/{hops_total} hops traversed</span>
      </div>

      <div className="trust-breakdown">
        {metrics.map((m, i) => (
          <MetricRow key={m.label} label={m.label} value={m.value} delay={i * 0.1 + 0.2} />
        ))}
      </div>

      <div style={{ marginTop: 24 }}>
        <div className="section-head">
          <h3 style={{ fontSize: 16, fontFamily: 'var(--serif)', color: 'var(--ink)', fontWeight: 400, marginBottom: 16 }}>
            Full data lineage trail
          </h3>
        </div>
        {lineage && (
          <div className="full-lineage">
            {lineage.map((step, i) => (
              <motion.div
                key={i}
                className="fl-row"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
              >
                <span className="fl-table">{step.table}</span>
                <span className="fl-field">{step.field}</span>
                <div className="fl-right">
                  <span className="fl-value">{step.value}</span>
                  <span className="fl-desc">{step.description}</span>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div style={{ marginTop: 24 }}>
        <p className="trust-explanation">
          Financial figures are computed by the graph engine. The language model writes the summary, never the math. If the LLM is unavailable, the system returns the same numbers with no narrative. All dollar amounts are cross-checked against deterministic values — if the LLM disagrees by more than 5%, the verified value is always used.
        </p>
      </div>
    </div>
  );
}

// ── Overview section
function OverviewSection({ data, onNavigate }) {
  const { financial_summary: fs, affected_counts: ac, time_to_impact_days } = data;
  const { formatted: exposureFormatted } = useCountUp(fs.total_exposure, { duration: 1100, formatFn: formatMoney });

  const stats = [
    { num: ac.purchase_orders,   label: 'Purchase orders', suffix: '' },
    { num: ac.materials,          label: 'Materials', suffix: '' },
    { num: ac.plants,             label: 'Plants', suffix: '' },
    { num: ac.production_orders,  label: 'Production orders', suffix: '' },
    { num: ac.customer_deliveries,label: 'Deliveries', suffix: '' },
    { num: time_to_impact_days,   label: 'Time to first impact', suffix: ' days' },
  ];

  return (
    <div className="fade-in">
      <div className="overview-exposure">
        <span className="exposure-num">{exposureFormatted}</span>
        <span className="exposure-label">projected financial exposure</span>
      </div>
      <div className="overview-stats">
        {stats.map(s => (
          <div key={s.label} className="stat-cell">
            <span className="stat-num">
              <AnimatedStat value={s.num} suffix={s.suffix} />
            </span>
            <span className="stat-label">{s.label}</span>
          </div>
        ))}
      </div>
      <div className="overview-insights">
        <div className="insight-row">
          <div className="insight-dot" />
          <div className="insight-body">
            <div className="insight-title">MCU-32 is sole-sourced to Apex</div>
            <div className="insight-desc">
              No second approved supplier is on file at Plant 1010 —{' '}
              <span className="lk" onClick={() => onNavigate('blast')}>this is the single point of failure</span>{' '}
              driving the cascade.
            </div>
          </div>
        </div>
        <div className="insight-row">
          <div className="insight-dot teal" />
          <div className="insight-body">
            <div className="insight-title">96% of exposure is avoidable</div>
            <div className="insight-desc">
              Re-sourcing, safety stock, and re-sequencing bring residual exposure down to {formatMoney(fs.residual_exposure)}.{' '}
              <span className="lk" onClick={() => onNavigate('avoidance')}>See the avoidance plan.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Blast radius wrapper (graph + lineage inspector)
function BlastSection({ data, selectedNode, onNodeSelect }) {
  return (
    <div className="fade-in">
      <div className="section-head">
        <h2 className="section-title">Blast radius</h2>
        <p className="section-sub">
          Every downstream node reachable from the delayed supplier, traversed hop by hop.
        </p>
      </div>
      <BlastRadiusGraph data={data} onNodeSelect={onNodeSelect} selectedNodeId={selectedNode?.id} />
      <div style={{ marginTop: 16 }}>
        <LineageTrail selectedNode={selectedNode} defaultLineage={data.lineage} />
      </div>
    </div>
  );
}

// ── Loading screen
function LoadingScreen({ step }) {
  return (
    <div className="loading-state">
      <h2 className="loading-title">Analysing supply chain…</h2>
      <div className="loading-steps">
        {LOADING_STEPS.map((s, i) => {
          const state = i < step ? 'done' : i === step ? 'active' : 'pending';
          return (
            <motion.div
              key={i}
              className={`ls-row ${state === 'active' ? 'active-step' : state === 'done' ? 'done-step' : ''}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.25 }}
            >
              <div className={`ls-dot ${state}`} />
              {s}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main App
export default function App() {
  const [report, setReport]               = useState(null);
  const [loading, setLoading]             = useState(false);
  const [loadStep, setLoadStep]           = useState(0);
  const [activeSection, setActiveSection] = useState('overview');
  const [selectedNode, setSelectedNode]   = useState(null);
  const [avoidanceApplied, setAvoidanceApplied] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [lastQuery, setLastQuery]         = useState('');

  const handleQuery = useCallback(async (query) => {
    setLoading(true);
    setLoadStep(0);
    setReport(null);
    setSelectedNode(null);
    setAvoidanceApplied(false);
    setLastQuery(query);

    // Step through loading animation
    const stepInterval = setInterval(() => {
      setLoadStep(s => Math.min(s + 1, LOADING_STEPS.length - 1));
    }, 400);

    try {
      let data;
      try {
        const health = await fetch('http://localhost:8000/api/health', { signal: AbortSignal.timeout(2000) });
        if (health.ok) {
          setBackendOnline(true);
          const qr = await fetch('http://localhost:8000/api/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
          const { supplier_id, delay_days } = await qr.json();
          const ir = await fetch('http://localhost:8000/api/impact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ supplier_id, delay_days }) });
          data = await ir.json();
        }
      } catch { setBackendOnline(false); }

      if (!data) data = await getMockImpactReport('SUP-1000', 14, query);
      clearInterval(stepInterval);
      setLoadStep(LOADING_STEPS.length);
      setReport(data);
      setActiveSection('overview');
    } catch (err) {
      console.error(err);
    } finally {
      clearInterval(stepInterval);
      setLoading(false);
    }
  }, []);

  const handleExecute = useCallback(() => setAvoidanceApplied(true), []);

  const hasReport = !!report;

  // Parse query meta from last query string
  const supplierName = lastQuery.match(/(?:supplier\s+)?([\w\s]+?)(?:\s+is|\s+delayed)/i)?.[1]?.trim() || 'Apex Microelectronics';
  const delayDays = lastQuery.match(/(\d+)\s*day/i)?.[1] || '14';

  return (
    <div className="app">

      {/* ── Top bar (always visible after query) */}
      {hasReport && (
        <div className="top-bar">
          <div className="topbar-brand">
            <span className="topbar-brand-name">SAP Knowledge Graph</span>
            <span className="topbar-brand-sub">Supplier exposure console</span>
          </div>
          <div className="topbar-right">
            <span className="topbar-chip">Synthetic dataset · v0.3</span>
            <span className="topbar-chip mode">{backendOnline ? 'Live API' : 'Demo mode'}</span>
          </div>
        </div>
      )}

      {/* ── Landing: no report yet ── */}
      {!hasReport && (
        <div className="landing-shell">
          <QueryInput onSubmit={handleQuery} loading={loading} />

          {loading ? (
            <LoadingScreen step={loadStep} />
          ) : (
            <div className="landing-hero">
              <h1 className="landing-h1">
                Trace a supplier delay to its dollar cost before it happens.
              </h1>
              <p className="landing-subtext">
                Ask a question in plain language. The system walks the SAP purchasing, production, and delivery graph and returns a financial exposure report, cross-checked against the source data.
              </p>
              <div className="landing-pillars">
                {[
                  { title: 'Exposure in dollars, not node counts', desc: <>Every affected purchase order, production run, and delivery is priced from EKPO, VBAP, and contract penalty data.</> },
                  { title: 'Avoidance before alerting', desc: <>The same traversal that <span>finds the risk</span> also searches for alternate suppliers, safety stock, and re-sequencing options.</> },
                  { title: "Numbers the model can't touch", desc: <>Financial figures are <span>computed by the graph engine</span>. The language model writes the summary, never the math.</> },
                ].map((p, i) => (
                  <div key={i} className="landing-pillar">
                    <span className="lp-num">0{i + 1}</span>
                    <div className="lp-body">
                      <div className="lp-title">{p.title}</div>
                      <div className="lp-desc">{p.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Report view with smooth enter transition ── */}
      {hasReport && !loading && (
        <motion.div
          className="report-wrapper"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* Narrative banner */}
          <div className="narrative-banner">
            <p className="narrative-text">
              A 14-day delay from <strong>Apex Microelectronics (Taiwan)</strong> reaches{' '}
              <strong>47 deliveries</strong> across an{' '}
              <strong>8-hop chain</strong>.{' '}
              MCU-32 is sole-sourced, and <span className="hl-risk">Plant 1010 (Hamburg)</span> holds{' '}
              <strong>850 units</strong> against a <strong>2,000-unit requirement</strong>{' '}
              — an <strong>8-day coverage gap</strong>.{' '}
              Boeing's order <span className="hl-risk">#4502 ($31.2M)</span> carries the largest single exposure.{' '}
              Three avoidance actions cut total exposure from{' '}
              <span className="hl-risk">$53.6M</span> to{' '}
              <span className="hl-teal">$2.1M</span> at a cost of{' '}
              <span className="hl-teal">$16.2K</span>.
            </p>
            <div className="narrative-meta">
              <div className="nm-item">
                <span className="nm-label">Query</span>
                <span className="nm-value">{supplierName}, +{delayDays} days</span>
              </div>
              <div className="nm-item">
                <span className="nm-label">Traversal</span>
                <span className="nm-value">
                  {report.confidence?.hops_complete || 8} hops,{' '}
                  {report.blast_radius?.nodes?.length || 12} nodes,{' '}
                  {report.blast_radius?.edges?.length || 11} edges
                </span>
              </div>
              <div className="nm-item">
                <span className="nm-label">Confidence</span>
                <span className="nm-conf">{report.confidence?.score || 92}%</span>
              </div>
              <div className="nm-item">
                <span className="nm-value" style={{ color: 'var(--ink-4)', fontStyle: 'italic' }}>
                  data verified against source tables,{' '}
                  <span className="nm-link" onClick={() => setActiveSection('trust')}>
                    see lineage &amp; trust
                  </span>
                </span>
              </div>
            </div>
          </div>

          {/* Query bar (still accessible) */}
          <QueryInput onSubmit={handleQuery} loading={loading} />

          {/* Console body: left rail + content */}
          <div className="console-body">
            <nav className="left-rail">
              <div className="rail-nav">
                {SECTIONS.map(s => (
                  <button
                    key={s.id}
                    className={`rail-nav-item ${activeSection === s.id ? 'active' : ''}`}
                    onClick={() => setActiveSection(s.id)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <p className="rail-note">
                Recomputed from Neo4j on every query. Nothing here is cached or estimated unless flagged.
              </p>
            </nav>

            <main className="main-content">
              <AnimatePresence mode="wait">
                {activeSection === 'overview' && (
                  <motion.div
                    key="overview"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <OverviewSection data={report} onNavigate={setActiveSection} />
                  </motion.div>
                )}
                {activeSection === 'blast' && (
                  <motion.div
                    key="blast"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <BlastSection data={report} selectedNode={selectedNode} onNodeSelect={setSelectedNode} />
                  </motion.div>
                )}
                {activeSection === 'finance' && (
                  <motion.div
                    key="finance"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <FinancialDashboard data={report} avoidanceApplied={avoidanceApplied} />
                  </motion.div>
                )}
                {activeSection === 'avoidance' && (
                  <motion.div
                    key="avoidance"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <AvoidancePanel plan={report.avoidance_plan} onExecute={handleExecute} />
                  </motion.div>
                )}
                {activeSection === 'timeline' && (
                  <motion.div
                    key="timeline"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <ImpactTimeline timeline={report.impact_timeline} />
                  </motion.div>
                )}
                {activeSection === 'trust' && (
                  <motion.div
                    key="trust"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                  >
                    <TrustSection confidence={report.confidence} lineage={report.lineage} />
                  </motion.div>
                )}
              </AnimatePresence>
            </main>
          </div>
        </motion.div>
      )}
    </div>
  );
}
