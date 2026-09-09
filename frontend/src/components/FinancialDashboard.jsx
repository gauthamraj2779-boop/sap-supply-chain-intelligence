import { motion } from 'framer-motion';

function formatMoney(val) {
  if (!val && val !== 0) return '—';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

const CATEGORIES = [
  { key: 'po_stranded_value',    label: 'PO stranded value',   src: 'EKPO.NETWR · open commitments',           desc: 'Idle plant cost × days halted' },
  { key: 'production_halt_cost', label: 'Production halt cost', src: 'AFKO.GLTRP · idle plant cost × days',     desc: 'Idle plant cost × days halted' },
  { key: 'revenue_at_risk',      label: 'Revenue at risk',      src: 'VBAP.NETWR · downstream sales orders',    desc: 'Downstream sales order value' },
  { key: 'penalty_exposure',     label: 'Penalty exposure',     src: 'LIKP.LFDAT · contractual late-delivery',  desc: 'Contractual late-delivery clauses' },
];

const CUSTOMERS = [
  { name: 'Boeing',          orders: 1, exposure: 31200000 },
  { name: 'Airbus',          orders: 2, exposure: 18700000 },
  { name: 'Lockheed Martin', orders: 2, exposure:  2800000 },
  { name: 'Raytheon',        orders: 1, exposure:   900000 },
];

export default function FinancialDashboard({ data, avoidanceApplied }) {
  if (!data) return null;
  const { financial_summary: fs } = data;
  const total = fs.total_exposure;
  const maxCust = CUSTOMERS[0].exposure;

  return (
    <div className="fin-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Financial exposure</h2>
        <p className="section-sub">
          {formatMoney(total)} across four categories, computed from PO, production, sales, and penalty data.
          {avoidanceApplied && <span style={{ color: 'var(--teal)', fontWeight: 500 }}> Avoidance actions reduce residual to {formatMoney(fs.residual_exposure)}.</span>}
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
          const pct = Math.round((val / total) * 100);
          return (
            <motion.div
              key={cat.key}
              className="ledger-row cat-grid"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.07, duration: 0.3 }}
            >
              <div className="lr-cat">
                <span className="lr-cat-name">{cat.label}</span>
                <span className="lr-cat-src">{cat.src}</span>
              </div>
              <span className="lr-amount">{formatMoney(val)}</span>
              <div className="lr-share-cell">
                <span className="lr-share-num">{pct}%</span>
                <div className="lr-share-bar-bg">
                  <motion.div
                    className="lr-share-bar"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ delay: i * 0.07 + 0.2, duration: 0.5 }}
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
            <span style={{ textAlign: 'center' }}>Orders</span>
            <span className="lh-right">Amount</span>
            <span className="lh-right">Share</span>
          </div>
          {CUSTOMERS.map((cust, i) => {
            const pct = Math.round((cust.exposure / total) * 100);
            const barPct = Math.round((cust.exposure / maxCust) * 100);
            return (
              <motion.div
                key={cust.name}
                className="ledger-row cust-grid"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.07, duration: 0.3 }}
              >
                <span className="lr-cust-name">{cust.name}</span>
                <span className="lr-orders">{cust.orders}</span>
                <span className="lr-amount">{formatMoney(cust.exposure)}</span>
                <div className="lr-share-cell">
                  <span className="lr-share-num">{pct}%</span>
                  <div className="lr-share-bar-bg">
                    <motion.div
                      className="lr-share-bar"
                      initial={{ width: 0 }}
                      animate={{ width: `${barPct}%` }}
                      transition={{ delay: i * 0.07 + 0.2, duration: 0.5 }}
                    />
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
