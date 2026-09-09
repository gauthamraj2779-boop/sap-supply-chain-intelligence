import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

function formatMoney(val) {
  if (!val && val !== 0) return '—';
  if (val === 0) return '$0';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

export default function AvoidancePanel({ plan, onExecute }) {
  const [executed, setExecuted] = useState({});

  if (!plan) return null;

  const markExecuted = (id) => {
    setExecuted(prev => ({ ...prev, [id]: true }));
    onExecute && onExecute(id);
  };

  return (
    <div className="avoidance-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Avoidance plan</h2>
        <p className="section-sub">
          Ranked actions the graph found by searching for alternate suppliers, buffer stock, and slack in the schedule.
        </p>
      </div>

      {/* Summary stats */}
      <div className="avoidance-summary-row">
        <div className="av-sum-stat">
          <span className="avs-num mid">{formatMoney(plan.total_avoidance_cost)}</span>
          <span className="avs-label">Total cost</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num teal">{formatMoney(plan.total_risk_mitigated)}</span>
          <span className="avs-label">Risk mitigated</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num mid">{plan.overall_roi?.toLocaleString()}×</span>
          <span className="avs-label">Return</span>
        </div>
      </div>

      {/* Numbered action list */}
      <div className="avoidance-list">
        {plan.actions.map((action, i) => {
          const isDone = executed[action.id];
          return (
            <motion.div
              key={action.id}
              className="action-item"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1, duration: 0.3 }}
            >
              <span className="ai-num">{i + 1}.</span>
              <div className="ai-body">
                <div className="ai-title" dangerouslySetInnerHTML={{
                  __html: action.title
                    .replace(/from ([^,]+),/, 'from <span>$1</span>,')
                    .replace(/from ([^.]+)\./, 'from <span>$1</span>.')
                    .replace(/#(\w+)/, '#<span>$1</span>')
                }} />
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
                  {action.lead_time_days > 0 && (
                    <div className="aim-group">
                      <span className="aim-val mid">{action.lead_time_days} days</span>
                      <span className="aim-label">Lead time</span>
                    </div>
                  )}
                  {action.lead_time_days === 0 && (
                    <div className="aim-group">
                      <span className="aim-val mid">—</span>
                      <span className="aim-label">No delay</span>
                    </div>
                  )}
                </div>

                <div className="ai-actions">
                  <AnimatePresence mode="wait">
                    {isDone ? (
                      <motion.span
                        key="done"
                        className="execute-btn done"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                      >
                        ✓ Marked as executed
                      </motion.span>
                    ) : (
                      <motion.button
                        key="btn"
                        className="execute-btn"
                        onClick={() => markExecuted(action.id)}
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

      {/* Residual footer */}
      <div className="avoidance-residual">
        <span className="ar-label">Residual exposure after all actions</span>
        <span className="ar-value">{formatMoney(plan.residual_exposure)}</span>
      </div>
    </div>
  );
}
