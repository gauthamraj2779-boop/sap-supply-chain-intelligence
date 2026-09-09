import { useState, useMemo } from 'react';
import { useAnimatedNumber, fmtUSD } from '../utils/useAnimatedNumber';

export default function AvoidancePanel({ plan, onExecute, executed = new Set(), setExecuted }) {
  const [localExecuted, setLocalExecuted] = useState(() => new Set());
  const [flashingId, setFlashingId] = useState(null);
  const [openEvidence, setOpenEvidence] = useState({});

  const activeExecuted = setExecuted ? executed : localExecuted;
  const updateExecuted = setExecuted || setLocalExecuted;

  const actions = plan?.actions ?? [];
  const exposureBefore = plan?.exposure_before ?? 0;

  // Totals reflect what has actually been marked executed. Residual falls from
  // the real starting exposure by the real mitigation of each action, so the
  // bar tracks the plan rather than a scripted sequence of milestones.
  const totals = useMemo(() => {
    const done = actions.filter((a) => activeExecuted.has(a.id));
    const totalCost = done.reduce((s, a) => s + a.cost, 0);
    const totalMitigated = done.reduce((s, a) => s + a.risk_mitigated, 0);
    const residual = Math.max(0, exposureBefore - totalMitigated);
    const roi = totalCost > 0 ? Math.round(totalMitigated / totalCost) : 0;
    return { totalCost, totalMitigated, residual, count: done.length, roi };
  }, [activeExecuted, actions, exposureBefore]);

  const costDisplay = useAnimatedNumber(totals.totalCost, fmtUSD);
  const mitigatedDisplay = useAnimatedNumber(totals.totalMitigated, fmtUSD);
  const residualDisplay = useAnimatedNumber(totals.residual, fmtUSD);
  const roiDisplay = useAnimatedNumber(totals.roi, (v) => `${Math.round(v).toLocaleString()}×`);

  const residualPct = exposureBefore > 0
    ? Math.max(2, Math.min(100, (totals.residual / exposureBefore) * 100))
    : 0;
  const resolved = residualPct <= 15;

  if (!plan) return null;

  if (actions.length === 0) {
    return (
      <div className="avoidance-section fade-in">
        <div className="section-head">
          <h2 className="section-title">Avoidance plan</h2>
          <p className="section-sub">
            No actions needed — this delay produces no material shortfall, so there
            is nothing to re-source, transfer, or re-sequence.
          </p>
        </div>
      </div>
    );
  }

  function toggleExecuted(id) {
    updateExecuted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        setFlashingId(id);
        onExecute?.(id);
      }
      return next;
    });
  }

  return (
    <div className="avoidance-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Avoidance plan</h2>
        <p className="section-sub">
          Ranked actions the graph found by searching for alternate suppliers, buffer
          stock, and slack in the schedule — allocated cheapest-first by cost per unit
          covered. Mark actions executed to see residual exposure fall.
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
        {actions.map((action, i) => {
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
                    <span className="aim-val teal">{fmtUSD(action.risk_mitigated)}</span>
                    <span className="aim-label">Risk mitigated</span>
                  </div>
                  {action.roi != null && (
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

                {action.evidence?.length > 0 && (
                  <div className="ai-evidence">
                    <button
                      className="ai-evidence-toggle"
                      onClick={() =>
                        setOpenEvidence((prev) => ({ ...prev, [action.id]: !prev[action.id] }))
                      }
                    >
                      {openEvidence[action.id] ? '− Hide' : '+ Show'} SAP evidence
                      {' '}({action.evidence.length})
                    </button>
                    {openEvidence[action.id] && (
                      <ul className="ai-evidence-list">
                        {action.evidence.map((e, k) => <li key={k}>{e}</li>)}
                      </ul>
                    )}
                  </div>
                )}

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
              : `${totals.count} of ${actions.length} actions executed`}
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

      {plan.rejected?.length > 0 && (
        <div className="rejected-block">
          <h3 className="subsection-title">Considered and rejected</h3>
          <p className="section-sub">
            Feasible options the engine priced and did not take.
          </p>
          {plan.rejected.map((r, i) => (
            <div key={i} className="rejected-row">
              <span className="rj-summary">{r.summary}</span>
              <span className="rj-cost">${r.unit_cost}/unit</span>
              <span className="rj-reason">{r.reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
