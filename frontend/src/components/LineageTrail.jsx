import { motion } from 'framer-motion';

/**
 * Lineage inspector. Shows the SAP provenance carried by the selected graph
 * node; with nothing selected it falls back to the report's critical path —
 * the trail behind the single largest exposure.
 */
export default function LineageTrail({ selectedNode, defaultLineage, defaultTitle }) {
  const nodeLineage = selectedNode?.lineage?.steps?.map((s) => ({
    table: s.sap_table,
    field: s.sap_field,
    value: s.value,
    description: s.meaning,
    key: s.key,
  }));

  const lineage = nodeLineage?.length ? nodeLineage : defaultLineage;
  const derivation = selectedNode?.lineage?.derivation;
  const title = selectedNode
    ? `${selectedNode.type} — ${selectedNode.label}`
    : defaultTitle || 'Critical path';

  return (
    <div className="lineage-inspector">
      <div className="li-left">
        <div className="li-title">
          {selectedNode ? 'Selected node' : 'Critical path'} — {title}
        </div>
        {!lineage || lineage.length === 0 ? (
          <p className="li-empty">
            Click any node in the graph to inspect its source record.
          </p>
        ) : (
          <>
            <div className="li-trail">
              {lineage.map((step, i) => (
                <motion.div
                  key={`${step.table}-${step.field}-${i}`}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: Math.min(i, 10) * 0.05 }}
                >
                  <div className="li-trail-row">
                    <span className="ltr-table">{step.table}</span>
                    <span className="ltr-field">{step.field}</span>
                    <span className="ltr-value">{step.value}</span>
                    <span className="ltr-desc">{step.description}</span>
                  </div>
                </motion.div>
              ))}
            </div>
            {derivation && <p className="li-derivation">{derivation}</p>}
          </>
        )}
      </div>

      <div className="li-right">
        <div className="li-title">Source record</div>
        {selectedNode ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
              <strong>{selectedNode.label}</strong>
            </p>
            <p style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.6 }}>
              SAP table:{' '}
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink)' }}>
                {selectedNode.sap_table || '—'}
              </span>
            </p>
            {selectedNode.sap_fields &&
              Object.entries(selectedNode.sap_fields).map(([k, v]) => (
                <div
                  key={k}
                  style={{ display: 'flex', gap: 8, fontSize: 12, fontFamily: 'var(--mono)' }}
                >
                  <span style={{ color: 'var(--ink-4)', minWidth: 76 }}>{k}</span>
                  <span style={{ color: 'var(--ink)' }}>{String(v)}</span>
                </div>
              ))}
            {typeof selectedNode.exposure === 'number' && selectedNode.exposure > 0 && (
              <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4 }}>
                Exposure carried by this node:{' '}
                <strong>${Math.round(selectedNode.exposure).toLocaleString()}</strong>
              </p>
            )}
          </div>
        ) : (
          <p className="li-empty">
            The lineage panel updates in place — this is how the deterministic engine
            proves its numbers rather than asserting them.
          </p>
        )}
      </div>
    </div>
  );
}
