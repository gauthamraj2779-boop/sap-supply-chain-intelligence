import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAnimatedNumber } from '../utils/useAnimatedNumber';

function formatMoney(val) {
  if (!val && val !== 0) return '—';
  if (val === 0) return '$0';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

export default function AvoidancePanel({ plan, onExecute }) {
  // Set in useState tracks executed action IDs
  const [executedIds, setExecutedIds] = useState(() => new Set());

  // Baseline exposure if no actions are executed
  const baselineExposure = useMemo(() => {
    if (!plan) return 0;
    return (plan.total_risk_mitigated || 0) + (plan.residual_exposure || 0);
  }, [plan]);

  // Totals calculated dynamically via useMemo based on executed Set
  const { totalCost, totalMitigated, residualExposure, overallRoi, executedCount } = useMemo(() => {
    if (!plan?.actions) {
      return { totalCost: 0, totalMitigated: 0, residualExposure: 0, overallRoi: 0, executedCount: 0 };
    }

    const executedActions = plan.actions.filter(a => executedIds.has(a.id));
    const cost = executedActions.reduce((sum, a) => sum + (a.cost || 0), 0);
    const mitigated = executedActions.reduce((sum, a) => sum + (a.risk_mitigated || 0), 0);
    const residual = Math.max(0, baselineExposure - mitigated);
    const roi = cost > 0 ? Math.round(mitigated / cost) : (plan.overall_roi || 0);

    return {
      totalCost: cost,
      totalMitigated: mitigated,
      residualExposure: residual,
      overallRoi: roi,
      executedCount: executedActions.length,
    };
  }, [plan, executedIds, baselineExposure]);

  // useAnimatedNumber animates smoothly between two arbitrary values as clicks occur
  const { formatted: animCost } = useAnimatedNumber(totalCost, { formatFn: formatMoney });
  const { formatted: animMitigated } = useAnimatedNumber(totalMitigated, { formatFn: formatMoney });
  const { formatted: animResidual } = useAnimatedNumber(residualExposure, { formatFn: formatMoney });
  const { formatted: animRoi } = useAnimatedNumber(overallRoi, {
    formatFn: (v) => (v > 0 ? `${v.toLocaleString()}×` : '—'),
  });

  if (!plan) return null;

  const toggleExecuted = (id) => {
    setExecutedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
    onExecute && onExecute(id);
  };

  const allExecuted = plan.actions?.length > 0 && executedCount === plan.actions.length;

  return (
    <div className="avoidance-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Avoidance plan</h2>
        <p className="section-sub">
          Ranked actions the graph found by searching for alternate suppliers, buffer stock, and slack in the schedule.
        </p>
      </div>

      {/* Live animated summary stats */}
      <div className="avoidance-summary-row">
        <div className="av-sum-stat">
          <span className="avs-num mid">{animCost}</span>
          <span className="avs-label">Total cost committed</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num teal">{animMitigated}</span>
          <span className="avs-label">Risk mitigated</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num mid">{animRoi}</span>
          <span className="avs-label">Realized return</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num" style={{ color: residualExposure > 2100000 ? 'var(--risk)' : 'var(--teal)' }}>
            {animResidual}
          </span>
          <span className="avs-label">Residual exposure</span>
        </div>
      </div>

      {/* Numbered action list */}
      <div className="avoidance-list">
        {plan.actions.map((action, i) => {
          const isDone = executedIds.has(action.id);
          return (
            <motion.div
              key={action.id}
              className={`action-item ${isDone ? 'executed' : ''}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.3 }}
              style={{
                borderColor: isDone ? 'var(--teal)' : 'var(--rule)',
                backgroundColor: isDone ? 'rgba(13, 98, 112, 0.03)' : '#fff',
                transition: 'border-color 0.3s, background-color 0.3s',
              }}
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
                    <span className="aim-val neutral">{formatMoney(action.cost)}</span>
                    <span className="aim-label">Cost</span>
                  </div>
                  <div className="aim-group">
                    <span className="aim-val teal">{formatMoney(action.risk_mitigated)}</span>
                    <span className="aim-label">Risk mitigated</span>
                  </div>
                  {action.roi !== null && (
                    <div className="aim-group">
                      <span className="aim-val mid">{action.roi?.toLocaleString()}×</span>
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
                  <AnimatePresence mode="wait">
                    {isDone ? (
                      <motion.button
                        key="done-btn"
                        className="execute-btn done"
                        onClick={() => toggleExecuted(action.id)}
                        whileTap={{ scale: 0.97 }}
                        title="Click to revert action"
                      >
                        ✓ Marked as executed (Undo)
                      </motion.button>
                    ) : (
                      <motion.button
                        key="execute-btn"
                        className="execute-btn"
                        onClick={() => toggleExecuted(action.id)}
                        whileTap={{ scale: 0.97 }}
                      >
                        Mark as executed
                      </motion.button>
                    )}
                  </AnimatePresence>
                  <span style={{ fontSize: 11, color: 'var(--ink-4)', fontFamily: 'var(--mono)' }}>
                    {action.sap_table}
                  </span>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Residual milestone tracker */}
      <div className="avoidance-residual" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="ar-label">
            {allExecuted
              ? 'All avoidance actions executed · Maximum risk avoided'
              : `${executedCount} of ${plan.actions?.length || 3} actions executed`}
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
            color: residualExposure > 2100000 ? 'var(--risk)' : 'var(--teal)',
          }}
        >
          {animResidual}
        </span>
      </div>
    </div>
  );
}
