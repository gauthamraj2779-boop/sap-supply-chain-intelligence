import { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import QueryInput from './components/QueryInput';
import BlastRadiusGraph from './components/BlastRadiusGraph';
import FinancialDashboard from './components/FinancialDashboard';
import AvoidancePanel from './components/AvoidancePanel';
import ImpactTimeline from './components/ImpactTimeline';
import LineageTrail from './components/LineageTrail';
import { analyseQuestion, checkHealth, ApiError } from './utils/api';
import { formatMoney, formatQty } from './utils/format';

const SECTIONS = [
  { id: 'overview',  label: 'Overview' },
  { id: 'blast',     label: 'Blast radius' },
  { id: 'finance',   label: 'Financial exposure' },
  { id: 'avoidance', label: 'Avoidance plan' },
  { id: 'timeline',  label: 'Timeline' },
  { id: 'trust',     label: 'Lineage & trust' },
];

const LOADING_STEPS = [
  'Parsing query and resolving entity…',
  'Traversing the supply chain graph…',
  'Computing financial exposure per hop…',
  'Searching for avoidance paths…',
  'Cross-checking and scoring confidence…',
];

// ── Lineage & trust ────────────────────────────────────────────────────────
function TrustSection({ confidence, lineage, subject, derivation, assumptions }) {
  if (!confidence) return null;
  const metrics = [
    { label: 'Data completeness',  value: confidence.data_completeness },
    { label: 'Traversal coverage', value: confidence.traversal_coverage },
    { label: 'Engine agreement',   value: confidence.engine_agreement },
  ];

  return (
    <div className="trust-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Lineage &amp; trust</h2>
        <p className="section-sub">
          Every figure is computed deterministically from the graph — the language
          model writes the narrative, never the maths.
        </p>
      </div>

      <div className="trust-score-row">
        <span className="trust-pct">{confidence.score}%</span>
        <span className="trust-label">
          confidence score · {confidence.hops_complete}/{confidence.hops_total} hops traversed
        </span>
      </div>

      <div className="trust-breakdown">
        {metrics.map((m, i) => (
          <div key={m.label} className="trust-metric">
            <div className="tm-head">
              <span className="tm-name">{m.label}</span>
              <span className="tm-val">{m.value}%</span>
            </div>
            <div className="tm-bar-bg">
              <motion.div
                className="tm-bar"
                initial={{ width: 0 }}
                animate={{ width: `${m.value}%` }}
                transition={{ delay: i * 0.1 + 0.2, duration: 0.6 }}
              />
            </div>
          </div>
        ))}
      </div>

      {confidence.formula && (
        <p className="trust-formula">{confidence.formula}</p>
      )}

      {confidence.degraded_modes?.length > 0 && (
        <div className="degraded-list">
          <span className="degraded-title">Running degraded</span>
          {confidence.degraded_modes.map((d) => (
            <span key={d} className="degraded-chip">{d.replace(/_/g, ' ')}</span>
          ))}
        </div>
      )}

      {confidence.notes?.length > 0 && (
        <ul className="trust-notes">
          {confidence.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}

      {lineage?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div className="section-head">
            <h3 className="subsection-title">Critical path — full data lineage</h3>
            {subject && <p className="section-sub">{subject}</p>}
          </div>
          <div className="full-lineage">
            {lineage.map((step, i) => (
              <motion.div
                key={i}
                className="fl-row"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(i, 12) * 0.05 }}
              >
                <span className="fl-table">{step.table}</span>
                <span className="fl-field">{step.field}</span>
                <div className="fl-right">
                  <span className="fl-value">{step.value}</span>
                  <span className="fl-desc">{step.description}</span>
                  {step.key && <span className="fl-key">{step.key}</span>}
                </div>
              </motion.div>
            ))}
          </div>
          {derivation && <p className="fl-derivation">{derivation}</p>}
        </div>
      )}

      {assumptions?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 className="subsection-title">Declared assumptions</h3>
          <p className="section-sub">
            Figures that are not SAP fields. Stated here rather than buried in the
            calculation.
          </p>
          <ul className="assumption-list">
            {assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Overview ───────────────────────────────────────────────────────────────
function OverviewSection({ data, onNavigate }) {
  const { financial_summary: fs, affected_counts: ac, time_to_impact_days } = data;

  const stats = [
    { num: ac.purchase_orders,   label: 'Purchase orders' },
    { num: ac.materials_short,   label: 'Materials short' },
    { num: ac.plants,            label: 'Plants' },
    { num: ac.production_orders, label: 'Production orders' },
    { num: ac.deliveries,        label: 'Deliveries' },
    {
      num: time_to_impact_days === null ? '—' : `${time_to_impact_days} days`,
      label: 'Time to first impact',
    },
  ];

  // Insights are derived from the report, not authored copy.
  const insights = [];
  const worst = [...(data.materials || [])]
    .filter((m) => m.shortfall_qty > 0)
    .sort((a, b) => b.shortfall_qty * b.unit_cost - a.shortfall_qty * a.unit_cost)[0];
  const sole = data.supplier?.sole_source_materials || [];

  if (sole.length > 0) {
    const cascaded = fs.total_exposure > 0;
    insights.push({
      tone: cascaded ? 'risk' : 'neutral',
      title: `${sole.join(', ')} ${sole.length === 1 ? 'is' : 'are'} sole-sourced to ${data.supplier.name}`,
      body: cascaded ? (
        <>
          No second approved supplier is on file in EINA/EINE —{' '}
          <span className="lk" onClick={() => onNavigate('blast')}>
            this is the single point of failure
          </span>{' '}
          driving the cascade.
        </>
      ) : (
        <>
          No second approved supplier is on file in EINA/EINE. Stock currently
          absorbs the delay, so this is a standing structural risk rather than an
          active one.
        </>
      ),
    });
  }
  if (worst) {
    insights.push({
      tone: 'risk',
      title: `${worst.matnr} at plant ${worst.werks} is short ${formatQty(worst.shortfall_qty)} units`,
      body: (
        <>
          {formatQty(worst.on_hand_qty)} on hand against {formatQty(worst.required_qty)}{' '}
          required before the revised arrival —{' '}
          {worst.days_of_coverage >= 9999
            ? 'no consumption recorded in the horizon'
            : `${worst.days_of_coverage.toFixed(1)} days of coverage`}
          .
        </>
      ),
    });
  }
  if (data.avoidance_plan?.actions?.length > 0) {
    insights.push({
      tone: 'teal',
      title: `${Math.round(fs.risk_mitigated_pct)}% of exposure is avoidable`,
      body: (
        <>
          {data.avoidance_plan.actions.length} actions costing{' '}
          {formatMoney(data.avoidance_plan.total_avoidance_cost)} bring residual exposure
          down to {formatMoney(fs.residual_exposure)}.{' '}
          <span className="lk" onClick={() => onNavigate('avoidance')}>
            See the avoidance plan.
          </span>
        </>
      ),
    });
  }
  if (fs.total_exposure === 0) {
    insights.push({
      tone: 'teal',
      title: 'No material exposure from this delay',
      body: <>Stock on hand covers every requirement inside the horizon, so no
        production order, delivery or customer is affected.</>,
    });
  }

  return (
    <div className="fade-in">
      <div className="overview-exposure">
        <span className="exposure-num">{formatMoney(fs.total_exposure)}</span>
        <span className="exposure-label">projected financial exposure</span>
      </div>

      <div className="overview-stats">
        {stats.map((s) => (
          <div key={s.label} className="stat-cell">
            <span className="stat-num">{s.num}</span>
            <span className="stat-label">{s.label}</span>
          </div>
        ))}
      </div>

      <div className="overview-insights">
        {insights.map((ins, i) => (
          <div key={i} className="insight-row">
            <div className={`insight-dot ${ins.tone === 'teal' ? 'teal' : ''}`} />
            <div className="insight-body">
              <div className="insight-title">{ins.title}</div>
              <div className="insight-desc">{ins.body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Blast radius ───────────────────────────────────────────────────────────
function BlastSection({ data, selectedNode, onNodeSelect }) {
  return (
    <div className="fade-in">
      <div className="section-head">
        <h2 className="section-title">Blast radius</h2>
        <p className="section-sub">
          Every downstream node reachable from the delayed supplier, traversed hop by hop.
        </p>
      </div>
      <BlastRadiusGraph
        data={data}
        onNodeSelect={onNodeSelect}
        selectedNodeId={selectedNode?.id}
      />
      <div style={{ marginTop: 16 }}>
        <LineageTrail
          selectedNode={selectedNode}
          defaultLineage={data.lineage}
          defaultTitle={data.critical_path_subject}
        />
      </div>
    </div>
  );
}

// ── Narrative banner ───────────────────────────────────────────────────────
function NarrativeBanner({ data, onNavigate }) {
  const { financial_summary: fs, affected_counts: ac, supplier, narrative } = data;
  const worst = [...(data.deliveries || [])].sort(
    (a, b) => (b.order_value + b.penalty_amount) - (a.order_value + a.penalty_amount),
  )[0];
  const shortMat = [...(data.materials || [])]
    .filter((m) => m.shortfall_qty > 0)
    .sort((a, b) => b.shortfall_qty * b.unit_cost - a.shortfall_qty * a.unit_cost)[0];

  return (
    <div className="narrative-banner">
      {narrative.is_llm ? (
        <p className="narrative-text">{narrative.text}</p>
      ) : (
        <p className="narrative-text">
          A {data.delay_days}-day delay from{' '}
          <strong>{supplier.name}{supplier.country ? ` (${supplier.country})` : ''}</strong>
          {ac.deliveries > 0 ? (
            <>
              {' '}reaches <strong>{ac.deliveries} deliveries</strong> and{' '}
              <strong>{ac.customers} customers</strong> across{' '}
              <strong>{data.confidence.hops_complete} hops</strong>.
            </>
          ) : (
            <> reaches no downstream deliveries inside the horizon.</>
          )}
          {shortMat && (
            <>
              {' '}<span className="hl-risk">{shortMat.matnr}</span> at{' '}
              {shortMat.plant_name} holds{' '}
              <strong>{formatQty(shortMat.on_hand_qty)} units</strong> against a{' '}
              <strong>{formatQty(shortMat.required_qty)}-unit requirement</strong> — a
              shortfall of <strong>{formatQty(shortMat.shortfall_qty)}</strong>.
            </>
          )}
          {worst && (
            <>
              {' '}<span className="hl-risk">
                {worst.customer_name}'s delivery {worst.vbeln}
              </span>{' '}
              ({formatMoney(worst.order_value)}) carries the largest single exposure.
            </>
          )}
          {data.avoidance_plan?.actions?.length > 0 && (
            <>
              {' '}{data.avoidance_plan.actions.length} avoidance actions cut total exposure
              from <span className="hl-risk">{formatMoney(fs.total_exposure)}</span> to{' '}
              <span className="hl-teal">{formatMoney(fs.residual_exposure)}</span> at a cost
              of <span className="hl-teal">
                {formatMoney(data.avoidance_plan.total_avoidance_cost)}
              </span>.
            </>
          )}
        </p>
      )}

      <div className="narrative-meta">
        <div className="nm-item">
          <span className="nm-label">Query</span>
          <span className="nm-value">{supplier.name}, +{data.delay_days} days</span>
        </div>
        <div className="nm-item">
          <span className="nm-label">Traversal</span>
          <span className="nm-value">
            {data.confidence.hops_complete} hops, {data.blast_radius.nodes.length} nodes,{' '}
            {data.blast_radius.edges.length} edges
          </span>
        </div>
        <div className="nm-item">
          <span className="nm-label">Confidence</span>
          <span className="nm-conf">{data.confidence.score}%</span>
        </div>
        <div className="nm-item">
          <span className="nm-label">Summary</span>
          <span className="nm-value">
            {narrative.is_llm ? `written by ${narrative.source}` : 'composed from computed figures'}
          </span>
        </div>
        <div className="nm-item">
          <span className="nm-value" style={{ color: 'var(--ink-4)', fontStyle: 'italic' }}>
            verified against source tables,{' '}
            <span className="nm-link" onClick={() => onNavigate('trust')}>
              see lineage &amp; trust
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Loading ────────────────────────────────────────────────────────────────
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
              transition={{ delay: i * 0.15 }}
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

// ── Error ──────────────────────────────────────────────────────────────────
function ErrorPanel({ error, onDismiss }) {
  return (
    <div className="error-panel">
      <div className="error-head">
        <span className="error-title">Analysis could not run</span>
        <button className="error-dismiss" onClick={onDismiss}>Dismiss</button>
      </div>
      <p className="error-msg">{error.message}</p>
      {error.detail && typeof error.detail === 'object' && (
        <pre className="error-detail">{JSON.stringify(error.detail, null, 2)}</pre>
      )}
      <p className="error-hint">
        Nothing is shown from cache or sample data — if the backend cannot answer,
        this console shows nothing rather than something invented.
      </p>
    </div>
  );
}

// ── App ────────────────────────────────────────────────────────────────────
export default function App() {
  const [report, setReport]                 = useState(null);
  const [loading, setLoading]               = useState(false);
  const [loadStep, setLoadStep]             = useState(0);
  const [activeSection, setActiveSection]   = useState('overview');
  const [selectedNode, setSelectedNode]     = useState(null);
  const [avoidanceApplied, setAvoidanceApplied] = useState(false);
  const [health, setHealth]                 = useState(null);
  const [error, setError]                   = useState(null);

  // Probe the backend once so the console can state its real capabilities.
  useEffect(() => {
    let live = true;
    checkHealth()
      .then((h) => live && setHealth(h))
      .catch(() => live && setHealth(null));
    return () => { live = false; };
  }, []);

  const handleQuery = useCallback(async (question) => {
    setLoading(true);
    setLoadStep(0);
    setReport(null);
    setSelectedNode(null);
    setAvoidanceApplied(false);
    setError(null);

    const stepTimer = setInterval(
      () => setLoadStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1)),
      350,
    );

    try {
      const { view } = await analyseQuestion(question);
      setReport(view);
      setActiveSection('overview');
      checkHealth().then(setHealth).catch(() => {});
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(err.message || 'Unexpected error while analysing.'),
      );
    } finally {
      clearInterval(stepTimer);
      setLoading(false);
    }
  }, []);

  const hasReport = !!report;
  const backendOnline = !!health;
  const llmOnline = !!health?.llm?.available;

  return (
    <div className="app">
      {hasReport && (
        <div className="top-bar">
          <div className="topbar-brand">
            <span className="topbar-brand-name">SAP Knowledge Graph</span>
            <span className="topbar-brand-sub">Supplier exposure console</span>
          </div>
          <div className="topbar-right">
            {/* Each chip states one narrow fact. "Live API" was ambiguous —
                an SAP audience reads it as a live SAP connection, which this is
                not: the graph is SAP-structured but synthetic. */}
            <span
              className="topbar-chip"
              title="Records loaded into the graph. Synthetic data using real SAP table and field names — not a connection to an SAP system."
            >
              {health?.graph?.records ?? 0} synthetic SAP records · {health?.graph?.backend ?? '—'} graph
            </span>
            <span
              className={`topbar-chip mode ${backendOnline ? 'online' : 'offline'}`}
              title={
                backendOnline
                  ? 'The console reached the analysis backend. Every figure on screen was computed for this query.'
                  : 'The analysis backend is unreachable. No figures are shown — nothing is served from cache or sample data.'
              }
            >
              {backendOnline ? 'Computed live' : 'Backend unreachable'}
            </span>
            <span className={`topbar-chip ${llmOnline ? 'online' : ''}`}>
              {llmOnline
                ? `Narrative · ${health.llm.provider}`
                : 'Narrative off · figures unaffected'}
            </span>
          </div>
        </div>
      )}

      {!hasReport && (
        <div className="landing-shell">
          <QueryInput onSubmit={handleQuery} loading={loading} health={health} />

          {error && <ErrorPanel error={error} onDismiss={() => setError(null)} />}

          {loading ? (
            <LoadingScreen step={loadStep} />
          ) : (
            !error && (
              <div className="landing-hero">
                <h1 className="landing-h1">
                  Trace a supplier delay to its dollar cost before it happens.
                </h1>
                <p className="landing-subtext">
                  Ask a question in plain language. The system walks the SAP purchasing,
                  production, and delivery graph and returns a financial exposure report,
                  cross-checked against the source data.
                </p>
                <div className="landing-pillars">
                  {[
                    {
                      title: 'Exposure in dollars, not node counts',
                      desc: <>Every affected purchase order, production run, and delivery is priced from <span>EKPO</span>, <span>VBAP</span>, and contract penalty data.</>,
                    },
                    {
                      title: 'Avoidance before alerting',
                      desc: <>The same traversal that <span>finds the risk</span> also searches for alternate suppliers, safety stock, and re-sequencing options.</>,
                    },
                    {
                      title: "Numbers the model can't touch",
                      desc: <>Financial figures are <span>computed by the graph engine</span>. The language model writes the summary, never the math.</>,
                    },
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
            )
          )}
        </div>
      )}

      {hasReport && !loading && (
        <>
          <NarrativeBanner data={report} onNavigate={setActiveSection} />

          <QueryInput onSubmit={handleQuery} loading={loading} health={health} />

          {error && <ErrorPanel error={error} onDismiss={() => setError(null)} />}

          {report.warnings?.length > 0 && (
            <div className="warning-strip">
              {report.warnings.map((w, i) => <div key={i} className="warning-row">{w}</div>)}
            </div>
          )}

          <div className="console-body">
            <nav className="left-rail">
              <div className="rail-nav">
                {SECTIONS.map((s) => (
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
                Recomputed from the {health?.graph?.backend ?? 'graph'} backend on every
                query. Nothing here is cached or estimated unless flagged.
              </p>
            </nav>

            <main className="main-content">
              {/* A keyed motion.div, deliberately NOT wrapped in
                  AnimatePresence: under mode="wait" the exit animation never
                  completed here, so the outgoing section stayed mounted and the
                  incoming one never rendered. Keying on activeSection remounts
                  and fades in on every switch, with nothing to get stuck on. */}
              <motion.div
                key={activeSection}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
              >
                {activeSection === 'overview' && (
                  <OverviewSection data={report} onNavigate={setActiveSection} />
                )}
                {activeSection === 'blast' && (
                  <BlastSection
                    data={report}
                    selectedNode={selectedNode}
                    onNodeSelect={setSelectedNode}
                  />
                )}
                {activeSection === 'finance' && (
                  <FinancialDashboard data={report} avoidanceApplied={avoidanceApplied} />
                )}
                {activeSection === 'avoidance' && (
                  <AvoidancePanel
                    plan={report.avoidance_plan}
                    onExecute={() => setAvoidanceApplied(true)}
                  />
                )}
                {activeSection === 'timeline' && (
                  <ImpactTimeline timeline={report.impact_timeline} />
                )}
                {activeSection === 'trust' && (
                  <TrustSection
                    confidence={report.confidence}
                    lineage={report.lineage}
                    subject={report.critical_path_subject}
                    derivation={report.critical_path_derivation}
                    assumptions={report.financial_summary.assumptions}
                  />
                )}
              </motion.div>
            </main>
          </div>
        </>
      )}
    </div>
  );
}
