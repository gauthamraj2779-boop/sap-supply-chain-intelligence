import { useState, useMemo } from 'react';
import { useAnimatedNumber, fmtUSD } from '../utils/useAnimatedNumber';

const ACTIONS = [
  {
    id: 'act-1',
    cost: 12000,
    mitigated: 31200000,
    roi: 2600,
    lead_time_days: 4,
    sap_table: 'EINA/EINE',
    title: 'Re-source from Nova Components (Germany)',
    description: 'Re-source 1,200 units from Nova Components GmbH. Stock available, lead time 4 days vs 14-day delay.',
  },
  {
    id: 'act-2',
    cost: 4200,
    mitigated: 18700000,
    roi: 4452,
    lead_time_days: 2,
    sap_table: 'MARD',
    title: 'Deploy Safety Stock from Plant 1020 (Singapore)',
    description: 'Transfer 800 units from Singapore hub. Covers 6 additional days of production.',
  },
  {
    id: 'act-3',
    cost: 0,
    mitigated: 3700000,
    roi: null,
    lead_time_days: 0,
    sap_table: 'AFKO',
    title: 'Re-sequence Production Order #9003 → #9001',
    description: 'Delay non-critical Order #9003 by 3 days. Prioritize Order #9001 (Boeing). No contractual penalty on #9003.',
  },
];

const RESIDUAL_MILESTONES = [53600000, 22400000, 3700000, 2100000];
const TOTAL_EXPOSURE = 53600000;

export default function AvoidancePanel({ executed = new Set(), setExecuted }) {
  const [localExecuted, setLocalExecuted] = useState(() => new Set());
  const [flashingId, setFlashingId] = useState(null);

  // Support executed state passed from parent, or local fallback
  const activeExecuted = setExecuted ? executed : localExecuted;
  const updateExecuted = setExecuted || setLocalExecuted;

  const totals = useMemo(() => {
    const done = ACTIONS.filter((a) => activeExecuted.has(a.id));
    const totalCost = done.reduce((s, a) => s + a.cost, 0);
    const totalMitigated = done.reduce((s, a) => s + a.mitigated, 0);
    const residual = RESIDUAL_MILESTONES[done.length] ?? 2100000;
    const roi = totalCost > 0 ? Math.round(totalMitigated / totalCost) : 3309;
    return { totalCost, totalMitigated, residual, count: done.length, roi };
  }, [activeExecuted]);

  const costDisplay = useAnimatedNumber(totals.totalCost, fmtUSD);
  const mitigatedDisplay = useAnimatedNumber(totals.totalMitigated, fmtUSD);
  const residualDisplay = useAnimatedNumber(totals.residual, fmtUSD);
  const roiDisplay = useAnimatedNumber(totals.roi, (v) => `${Math.round(v).toLocaleString()}×`);

  const residualPct = Math.max(4, Math.min(100, (totals.residual / TOTAL_EXPOSURE) * 100));
  const resolved = residualPct <= 15;

  function toggleExecuted(id) {
    updateExecuted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        setFlashingId(id);
      }
      return next;
    });
  }

  return (
    <div className="avoidance-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Avoidance plan</h2>
        <p className="section-sub">
          Ranked actions the graph found by searching for alternate suppliers, buffer stock, and slack in the schedule.
        </p>
      </div>

      {/* Summary stats with animated numbers */}
      <div className="avoidance-summary-row">
        <div className="av-sum-stat">
          <span className="avs-num mid">{costDisplay}</span>
          <span className="avs-label">Total cost committed</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num teal">{mitigatedDisplay}</span>
          <span className="avs-label">Risk mitigated</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num mid">{roiDisplay}</span>
          <span className="avs-label">Realized return</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num" style={{ color: resolved ? 'var(--teal)' : 'var(--risk)' }}>
            {residualDisplay}
          </span>
          <span className="avs-label">Residual exposure</span>
        </div>
      </div>

      {/* Residual progress bar with color swap */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--ink-4)', fontFamily: 'var(--mono)', marginBottom: 6 }}>
          <span>RESIDUAL EXPOSURE PROGRESS</span>
          <span>{Math.round(residualPct)}% REMAINING</span>
        </div>
        <div className="residual-bar-track">
          <div
            className={`residual-bar-fill ${resolved ? 'mitigate' : 'risk'}`}
            style={{
              width: `${residualPct}%`,
              transition: 'width .7s cubic-bezier(.4,0,.2,1), background .4s ease',
            }}
          />
        </div>
      </div>

      {/* Action list with execution flash and toggle */}
      <div className="avoidance-list">
        {ACTIONS.map((action, i) => {
          const isDone = activeExecuted.has(action.id);
          const isFlashing = flashingId === action.id;

          return (
            <div
              key={action.id}
              className={`action-item ${isDone ? 'executed' : ''} ${isFlashing ? 'just-executed' : ''}`}
              onAnimationEnd={() => setFlashingId(null)}
            >
              <span className="ai-num" style={{ color: isDone ? 'var(--teal)' : 'var(--ink-4)' }}>
                {i + 1}.
              </span>
              <div className="ai-body">
                <div
                  className="ai-title"
                  dangerouslySetInnerHTML={{
                    __html: action.title
                      .replace(/from ([^,]+),/, 'from <span>$1</span>,')
                      .replace(/from ([^.]+)\./, 'from <span>$1</span>.')
                      .replace(/#(\w+)/, '#<span>$1</span>'),
                  }}
                />
                <p className="ai-desc">{action.description}</p>

                <div className="ai-metrics">
                  <div className="aim-group">
                    <span className="aim-val neutral">{fmtUSD(action.cost)}</span>
                    <span className="aim-label">Cost</span>
                  </div>
                  <div className="aim-group">
                    <span className="aim-val teal">{fmtUSD(action.mitigated)}</span>
                    <span className="aim-label">Risk mitigated</span>
                  </div>
                  {action.roi !== null && (
                    <div className="aim-group">
                      <span className="aim-val mid">{action.roi.toLocaleString()}×</span>
                      <span className="aim-label">Return</span>
                    </div>
                  )}
                  {action.lead_time_days > 0 ? (
                    <div className="aim-group">
                      <span className="aim-val mid">{action.lead_time_days} days</span>
                      <span className="aim-label">Lead time</span>
                    </div>
                  ) : (
                    <div className="aim-group">
                      <span className="aim-val mid">—</span>
                      <span className="aim-label">No delay</span>
                    </div>
                  )}
                </div>

                <div className="ai-actions">
                  {isDone ? (
                    <button
                      className="execute-btn done"
                      onClick={() => toggleExecuted(action.id)}
                      title="Click to revert action"
                    >
                      ✓ Executed (Undo)
                    </button>
                  ) : (
                    <button
                      className="execute-btn"
                      onClick={() => toggleExecuted(action.id)}
                    >
                      Mark as executed
                    </button>
                  )}
                  <span style={{ fontSize: 11, color: 'var(--ink-4)', fontFamily: 'var(--mono)' }}>
                    {action.sap_table}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Residual footer */}
      <div className="avoidance-residual" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="ar-label">
            {resolved
              ? 'All primary actions executed · 96% exposure avoided'
              : `${totals.count} of ${ACTIONS.length} actions executed`}
          </span>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            Residual financial exposure remaining in supply chain
          </div>
        </div>
        <span
          className="ar-value"
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 22,
            fontWeight: 600,
            color: resolved ? 'var(--teal)' : 'var(--risk)',
          }}
        >
          {residualDisplay}
        </span>
      </div>
    </div>
  );
}
