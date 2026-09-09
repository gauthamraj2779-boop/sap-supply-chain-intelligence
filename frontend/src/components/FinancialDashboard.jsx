import { motion } from 'framer-motion';
import { formatMoney, formatMoneyExact } from '../utils/format';

/**
 * Ledger view of the exposure. Both tables are driven entirely by the report:
 * the category rows read the financial summary, the customer rows read the
 * backend's own per-customer roll-up.
 */
const CATEGORIES = [
  {
    key: 'po_stranded_value',
    label: 'PO stranded value',
    src: 'EKPO.NETWR · open commitments on short materials',
    desc: 'Capital committed to goods that now arrive too late to use as planned',
  },
  {
    key: 'production_halt_cost',
    label: 'Production halt cost',
    src: 'AFKO.GLTRP · longest halt per plant × idle cost/day',
    desc: 'Concurrent halts at one plant share idle days and are not double-billed',
  },
  {
    key: 'revenue_at_risk',
    label: 'Revenue at risk',
    src: 'VBAP.NETWR · downstream sales order items',
    desc: 'Full net value of affected sales order items, as a worst case',
  },
  {
    key: 'penalty_exposure',
    label: 'Penalty exposure',
    src: 'LIKP.LFDAT · contractual late-delivery clauses',
    desc: 'Order value × contract penalty rate, where the delivery slips',
  },
];

export default function FinancialDashboard({ data, avoidanceApplied }) {
  if (!data) return null;
  const fs = data.financial_summary;
  const customers = data.customers ?? [];
  const total = fs.total_exposure;

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

  const maxCust = customers.length
    ? Math.max(...customers.map((c) => c.total_exposure))
    : 0;

  return (
    <div className="fin-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Financial exposure</h2>
        <p className="section-sub">
          {formatMoney(total)} across four categories, computed from PO, production,
          sales, and penalty data.
          {avoidanceApplied && (
            <span style={{ color: 'var(--teal)', fontWeight: 500 }}>
              {' '}Avoidance actions reduce residual to {formatMoney(fs.residual_exposure)}.
            </span>
          )}
        </p>
      </div>

      <div className="ledger">
        <div className="ledger-head cat-grid">
          <span>Category</span>
          <span className="lh-right">Amount</span>
          <span className="lh-right">Share</span>
        </div>
        {CATEGORIES.map((cat, i) => {
          const val = fs[cat.key] ?? 0;
          const pct = total ? Math.round((val / total) * 100) : 0;
          return (
            <motion.div
              key={cat.key}
              className="ledger-row cat-grid"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.07, duration: 0.3 }}
              title={cat.desc}
            >
              <div className="lr-cat">
                <span className="lr-cat-name">{cat.label}</span>
                <span className="lr-cat-src">{cat.src}</span>
              </div>
              <span className="lr-amount" title={formatMoneyExact(val)}>
                {formatMoney(val)}
              </span>
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
        <div className="ledger-row cat-grid ledger-total">
          <div className="lr-cat">
            <span className="lr-cat-name">Total exposure</span>
            <span className="lr-cat-src">
              {fs.components_reconcile
                ? 'components reconcile to the total'
                : 'components do not reconcile — treat the breakdown as authoritative'}
            </span>
          </div>
          <span className="lr-amount" title={formatMoneyExact(total)}>
            {formatMoney(total)}
          </span>
          <span />
        </div>
      </div>

      {customers.length > 0 && (
        <div>
          <div className="section-head" style={{ marginTop: 28 }}>
            <h3 className="section-title" style={{ fontSize: 18 }}>
              Exposure by{' '}
              <em style={{ fontStyle: 'italic', color: 'var(--teal)' }}>customer</em>
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
              const pct = total ? Math.round((cust.total_exposure / total) * 100) : 0;
              const barPct = maxCust
                ? Math.round((cust.total_exposure / maxCust) * 100)
                : 0;
              return (
                <motion.div
                  key={cust.kunnr}
                  className="ledger-row cust-grid"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.07, duration: 0.3 }}
                  title={
                    `Revenue at risk ${formatMoneyExact(cust.revenue_at_risk)} · ` +
                    `penalties ${formatMoneyExact(cust.penalty_exposure)}`
                  }
                >
                  <span className="lr-cust-name">{cust.customer_name}</span>
                  <span className="lr-orders">{cust.deliveries_at_risk}</span>
                  <span className="lr-amount">{formatMoney(cust.total_exposure)}</span>
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
      )}

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
