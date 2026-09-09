import { motion } from 'framer-motion';
import { useCountUp } from '../utils/useAnimatedNumber';

function formatMoney(val) {
  if (!val && val !== 0) return '—';
  if (val === 0) return '$0';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

// Reusable count-up span component for monetary figures
function AnimatedAmount({ value, delay = 0, isActive = true }) {
  const display = useCountUp(value, { active: isActive, duration: 750, delay, formatFn: formatMoney });
  return <span>{display}</span>;
}

const CATEGORIES = [
  { key: 'po_stranded_value',    label: 'PO stranded value',   src: 'EKPO.NETWR · open commitments',           desc: 'Idle plant cost × days halted' },
  { key: 'production_halt_cost', label: 'Production halt cost', src: 'AFKO.GLTRP · idle plant cost × days',     desc: 'Idle plant cost × days halted' },
  { key: 'revenue_at_risk',      label: 'Revenue at risk',      src: 'VBAP.NETWR · downstream sales orders',    desc: 'Downstream sales order value' },
  { key: 'penalty_exposure',     label: 'Penalty exposure',     src: 'LIKP.LFDAT · contractual late-delivery',  desc: 'Contractual late-delivery clauses' },
];

export default function FinancialDashboard({ data, avoidanceApplied, isActive = true }) {
  if (!data) return null;
  const { financial_summary: fs } = data;
  const total = fs.total_exposure;

  // Per-customer exposure is rolled up by the backend (financial.py), already
  // sorted by size. The UI never groups or sums it.
  const customers = data.customers ?? [];
  const maxCust = customers.length
    ? Math.max(...customers.map((c) => c.total_exposure))
    : 0;

  if (total === 0) {
    return (
      <div className="fin-section fade-in">
        <div className="section-head">
          <h2 className="section-title">Financial exposure</h2>
          <p className="section-sub">
            No exposure from this delay — stock on hand covers every requirement
            inside the horizon, so nothing strands, halts, or ships late.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fin-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Financial exposure</h2>
        <p className="section-sub">
          <AnimatedAmount value={total} delay={100} isActive={isActive} /> across four categories, computed from PO, production, sales, and penalty data.
          {avoidanceApplied && (
            <span style={{ color: 'var(--teal)', fontWeight: 500 }}>
              {' '}Avoidance actions reduce residual to <AnimatedAmount value={fs.residual_exposure} isActive={isActive} />.
            </span>
          )}
        </p>
      </div>

      {/* Category ledger */}
      <div className="ledger">
        <div className="ledger-head cat-grid">
          <span>Category</span>
          <span className="lh-right">Amount</span>
          <span className="lh-right">Share</span>
        </div>
        {CATEGORIES.map((cat, i) => {
          const val = fs[cat.key] || 0;
          const pct = total > 0 ? Math.round((val / total) * 100) : 0;
          return (
            <motion.div
              key={cat.key}
              className="ledger-row cat-grid"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08, duration: 0.3 }}
            >
              <div className="lr-cat">
                <span className="lr-cat-name">{cat.label}</span>
                <span className="lr-cat-src">{cat.src}</span>
              </div>
              <span className="lr-amount">
                <AnimatedAmount value={val} delay={i * 80 + 150} isActive={isActive} />
              </span>
              <div className="lr-share-cell">
                <span className="lr-share-num">{pct}%</span>
                <div className="lr-share-bar-bg">
                  <motion.div
                    className="lr-share-bar"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ delay: i * 0.08 + 0.25, duration: 0.6, ease: 'easeOut' }}
                  />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Customer ledger */}
      <div>
        <div className="section-head" style={{ marginTop: 28 }}>
          <h3 className="section-title" style={{ fontSize: 18 }}>
            Exposure by <em style={{ fontStyle: 'italic', color: 'var(--teal)' }}>customer</em>
          </h3>
        </div>
        <div className="ledger">
          <div className="ledger-head cust-grid">
            <span>Customer</span>
            <span style={{ textAlign: 'center' }}>Deliveries</span>
            <span className="lh-right">Amount</span>
            <span className="lh-right">Share</span>
          </div>
          {customers.map((cust, i) => {
            const pct = total > 0 ? Math.round((cust.total_exposure / total) * 100) : 0;
            const barPct = maxCust ? Math.round((cust.total_exposure / maxCust) * 100) : 0;
            return (
              <motion.div
                key={cust.kunnr}
                className="ledger-row cust-grid"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.08, duration: 0.3 }}
              >
                <span className="lr-cust-name">{cust.customer_name}</span>
                <span className="lr-orders">{cust.deliveries_at_risk}</span>
                <span className="lr-amount">
                  <AnimatedAmount value={cust.total_exposure} delay={i * 80 + 200} isActive={isActive} />
                </span>
                <div className="lr-share-cell">
                  <span className="lr-share-num">{pct}%</span>
                  <div className="lr-share-bar-bg">
                    <motion.div
                      className="lr-share-bar"
                      initial={{ width: 0 }}
                      animate={{ width: `${barPct}%` }}
                      transition={{ delay: i * 0.08 + 0.25, duration: 0.6, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {fs.assumptions?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 className="subsection-title">Assumptions behind these figures</h3>
          <ul className="assumption-list">
            {fs.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
