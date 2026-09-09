import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatMoney, formatMoneyExact, formatQty, formatRoi } from '../utils/format';

/**
 * The avoidance plan. Every action carries the SAP records that prove it is
 * feasible, and the options the engine evaluated and rejected are shown too —
 * a decision is more credible when the road not taken is visible.
 */
export default function AvoidancePanel({ plan, onExecute }) {
  const [executed, setExecuted] = useState({});
  const [openEvidence, setOpenEvidence] = useState({});

  if (!plan) return null;

  if (!plan.actions.length) {
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

  const markExecuted = (id) => {
    setExecuted((prev) => ({ ...prev, [id]: true }));
    onExecute?.(id);
  };

  return (
    <div className="avoidance-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Avoidance plan</h2>
        <p className="section-sub">
          Ranked actions the graph found by searching for alternate suppliers, buffer
          stock, and slack in the schedule — allocated cheapest-first by cost per unit
          covered.
        </p>
      </div>

      <div className="avoidance-summary-row">
        <div className="av-sum-stat">
          <span className="avs-num mid" title={formatMoneyExact(plan.total_avoidance_cost)}>
            {formatMoney(plan.total_avoidance_cost)}
          </span>
          <span className="avs-label">Total cost</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num teal" title={formatMoneyExact(plan.total_risk_mitigated)}>
            {formatMoney(plan.total_risk_mitigated)}
          </span>
          <span className="avs-label">Risk mitigated</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num mid">{formatRoi(plan.overall_roi)}</span>
          <span className="avs-label">Return</span>
        </div>
        <div className="avs-divider" />
        <div className="av-sum-stat">
          <span className="avs-num teal">{Math.round(plan.mitigation_pct)}%</span>
          <span className="avs-label">Exposure removed</span>
        </div>
      </div>

      <div className="avoidance-list">
        {plan.actions.map((action, i) => {
          const isDone = executed[action.id];
          const showEv = openEvidence[action.id];
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
                <div className="ai-title">{action.title}</div>
                <p className="ai-desc">{action.description}</p>

                <div className="ai-metrics">
                  <div className="aim-group">
                    <span className="aim-val neutral" title={formatMoneyExact(action.cost)}>
                      {formatMoney(action.cost)}
                    </span>
                    <span className="aim-label">Cost</span>
                  </div>
                  <div className="aim-group">
                    <span className="aim-val teal" title={formatMoneyExact(action.risk_mitigated)}>
                      {formatMoney(action.risk_mitigated)}
                    </span>
                    <span className="aim-label">Risk mitigated</span>
                  </div>
                  <div className="aim-group">
                    <span className="aim-val mid">{formatRoi(action.roi)}</span>
                    <span className="aim-label">Return</span>
                  </div>
                  <div className="aim-group">
                    <span className="aim-val mid">
                      {action.lead_time_days > 0 ? `${action.lead_time_days} days` : '—'}
                    </span>
                    <span className="aim-label">
                      {action.lead_time_days > 0 ? 'Lead time' : 'No delay'}
                    </span>
                  </div>
                  {action.units > 0 && (
                    <div className="aim-group">
                      <span className="aim-val mid">{formatQty(action.units)}</span>
                      <span className="aim-label">Units covered</span>
                    </div>
                  )}
                </div>

                {action.evidence?.length > 0 && (
                  <div className="ai-evidence">
                    <button
                      className="ai-evidence-toggle"
                      onClick={() =>
                        setOpenEvidence((p) => ({ ...p, [action.id]: !p[action.id] }))
                      }
                    >
                      {showEv ? '− Hide' : '+ Show'} SAP evidence ({action.evidence.length})
                    </button>
                    <AnimatePresence>
                      {showEv && (
                        <motion.ul
                          className="ai-evidence-list"
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                        >
                          {action.evidence.map((e, k) => <li key={k}>{e}</li>)}
                        </motion.ul>
                      )}
                    </AnimatePresence>
                  </div>
                )}

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
                  <span className="ai-sap-src">{action.sap_table}</span>
                </div>
              </div>
            </motion.div>
          );
        })}
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

      <div className="avoidance-residual">
        <span className="ar-label">Residual exposure after all actions</span>
        <span className="ar-value" title={formatMoneyExact(plan.residual_exposure)}>
          {formatMoney(plan.residual_exposure)}
        </span>
      </div>
    </div>
  );
}
