import { motion } from 'framer-motion';

function fmt(val) {
  if (!val && val !== 0) return '—';
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`;
  return `$${val}`;
}

export default function ImpactTimeline({ timeline }) {
  if (!timeline || timeline.length === 0) return null;

  // Split into above (even index) and below (odd index)
  const above = timeline.filter((_, i) => i % 2 === 0);
  const below  = timeline.filter((_, i) => i % 2 !== 0);

  // Column positions — each event gets an equal slot
  const cols = timeline.length;

  return (
    <div className="tl-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Timeline</h2>
        <p className="section-sub">
          When each domino falls — cumulative financial exposure at each event, if no action is taken.
        </p>
      </div>

      <div className="tl-track-wrap">
        {/* ── ABOVE cards ── */}
        <div className="tl-row tl-above">
          {timeline.map((event, i) => (
            <div key={i} className="tl-col">
              {i % 2 === 0 ? (
                <motion.div
                  className="tl-card"
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.12, duration: 0.3 }}
                >
                  <span className="tl-card-day">Day {event.day}</span>
                  <span className="tl-card-title">{event.event}</span>
                  <span className="tl-card-amount">{fmt(event.cumulative_exposure)} cumulative</span>
                </motion.div>
              ) : (
                <div className="tl-spacer" />
              )}
            </div>
          ))}
        </div>

        {/* ── Track line with dots ── */}
        <div className="tl-track-row">
          <div className="tl-line" />
          {timeline.map((_, i) => (
            <div key={i} className="tl-col tl-dot-col">
              <motion.div
                className="tl-dot"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.12 + 0.1, type: 'spring', stiffness: 400 }}
              />
            </div>
          ))}
        </div>

        {/* ── BELOW cards ── */}
        <div className="tl-row tl-below">
          {timeline.map((event, i) => (
            <div key={i} className="tl-col">
              {i % 2 !== 0 ? (
                <motion.div
                  className="tl-card"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.12, duration: 0.3 }}
                >
                  <span className="tl-card-day">Day {event.day}</span>
                  <span className="tl-card-title">{event.event}</span>
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
