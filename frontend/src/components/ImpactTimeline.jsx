import { motion } from 'framer-motion';

function fmt(val) {
  if (!val && val !== 0) return '—';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

// Stage each event belongs to, from the API's `kind` field. Colours the track
// dot and labels the card, so the cascade is readable without reading prose.
const KIND_LABEL = {
  trigger:        'Trigger',
  purchase_order: 'Procurement',
  material:       'Inventory',
  production:     'Production',
  delivery:       'Delivery',
};

export default function ImpactTimeline({ timeline }) {
  if (!timeline || timeline.length === 0) return null;

  return (
    <div className="tl-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Timeline</h2>
        <p className="section-sub">
          When each domino falls — cumulative financial exposure at each event, if no action is taken.
        </p>
      </div>

      <div className="tl-track-wrap">
        {/* ── ABOVE cards (even index: 0, 2, 4...) ── */}
        <div className="tl-row tl-above">
          {timeline.map((event, i) => (
            <div key={`above-${i}`} className="tl-col">
              {i % 2 === 0 ? (
                <motion.div
                  className="tl-card"
                  initial={{ opacity: 0, y: -12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 + 0.1, duration: 0.35, ease: 'easeOut' }}
                  whileHover={{ y: -3, transition: { duration: 0.15 } }}
                >
                  <span className="tl-card-day">
                    Day {event.day}
                    {event.type && (
                      <span className={`tl-kind kind-${event.type}`}>
                        {KIND_LABEL[event.type] || event.type}
                      </span>
                    )}
                  </span>
                  <span className="tl-card-title">{event.event}</span>
                  {event.detail && <span className="tl-card-detail">{event.detail}</span>}
                  <span className="tl-card-amount">{fmt(event.cumulative_exposure)} cumulative</span>
                </motion.div>
              ) : (
                <div className="tl-spacer" />
              )}
            </div>
          ))}
        </div>

        {/* ── Track line with dots (draws left-to-right) ── */}
        <div className="tl-track-row">
          <motion.div
            className="tl-line"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformOrigin: 'left center' }}
          />
          {timeline.map((_, i) => (
            <div key={`dot-${i}`} className="tl-col tl-dot-col">
              <motion.div
                className={`tl-dot kind-${timeline[i]?.type ?? "trigger"}`}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.1 + 0.18, type: 'spring', stiffness: 500, damping: 25 }}
              />
            </div>
          ))}
        </div>

        {/* ── BELOW cards (odd index: 1, 3, 5...) ── */}
        <div className="tl-row tl-below">
          {timeline.map((event, i) => (
            <div key={`below-${i}`} className="tl-col">
              {i % 2 !== 0 ? (
                <motion.div
                  className="tl-card"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 + 0.1, duration: 0.35, ease: 'easeOut' }}
                  whileHover={{ y: 3, transition: { duration: 0.15 } }}
                >
                  <span className="tl-card-day">
                    Day {event.day}
                    {event.type && (
                      <span className={`tl-kind kind-${event.type}`}>
                        {KIND_LABEL[event.type] || event.type}
                      </span>
                    )}
                  </span>
                  <span className="tl-card-title">{event.event}</span>
                  {event.detail && <span className="tl-card-detail">{event.detail}</span>}
                  <span className="tl-card-amount">{fmt(event.cumulative_exposure)} cumulative</span>
                </motion.div>
              ) : (
                <div className="tl-spacer" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
