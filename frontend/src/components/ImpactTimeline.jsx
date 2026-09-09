import { motion } from 'framer-motion';
import { formatMoney, formatMoneyExact } from '../utils/format';

const KIND_LABEL = {
  trigger:        'Trigger',
  purchase_order: 'Procurement',
  material:       'Inventory',
  production:     'Production',
  delivery:       'Delivery',
};

export default function ImpactTimeline({ timeline }) {
  if (!timeline?.length) return null;

  return (
    <div className="tl-section fade-in">
      <div className="section-head">
        <h2 className="section-title">Timeline</h2>
        <p className="section-sub">
          When each domino falls — cumulative financial exposure at each event, if no
          action is taken.
        </p>
      </div>

      <div className="tl-track-wrap">
        <div className="tl-row tl-above">
          {timeline.map((event, i) => (
            <div key={i} className="tl-col">
              {i % 2 === 0 ? (
                <TimelineCard event={event} index={i} direction={-10} />
              ) : (
                <div className="tl-spacer" />
              )}
            </div>
          ))}
        </div>

        <div className="tl-track-row">
          <div className="tl-line" />
          {timeline.map((event, i) => (
            <div key={i} className="tl-col tl-dot-col">
              <motion.div
                className={`tl-dot kind-${event.type}`}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.09 + 0.1, type: 'spring', stiffness: 400 }}
                title={KIND_LABEL[event.type] || event.type}
              />
            </div>
          ))}
        </div>

        <div className="tl-row tl-below">
          {timeline.map((event, i) => (
            <div key={i} className="tl-col">
              {i % 2 !== 0 ? (
                <TimelineCard event={event} index={i} direction={10} />
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

function TimelineCard({ event, index, direction }) {
  return (
    <motion.div
      className="tl-card"
      initial={{ opacity: 0, y: direction }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.09, duration: 0.3 }}
      title={event.detail}
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
      <span className="tl-card-detail">{event.detail}</span>
      <span className="tl-card-amount" title={formatMoneyExact(event.cumulative_exposure)}>
        {formatMoney(event.cumulative_exposure)} cumulative
      </span>
    </motion.div>
  );
}
