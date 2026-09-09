/**
 * Lineage inspector.
 *
 * Card design and the key-based cross-fade come from the visual pass; the rows
 * are the real SAP provenance carried by the selected graph node. With nothing
 * selected it falls back to the report's critical path — the trail behind the
 * single largest exposure — so the panel is never empty and never invented.
 */
export default function LineageTrail({ selectedNode, defaultLineage, defaultTitle }) {
  const nodeRows = selectedNode?.lineage?.steps?.map((s) => ({
    table: s.sap_table,
    field: s.sap_field,
    value: s.value,
    description: s.meaning,
    key: s.key,
  }));

  const rows = nodeRows?.length ? nodeRows : defaultLineage ?? [];
  const derivation = selectedNode?.lineage?.derivation;
  const title = selectedNode
    ? `${selectedNode.type} — ${selectedNode.label}`
    : defaultTitle || 'Critical path';

  // Remounting on selection change drives the CSS cross-fade.
  const remountKey = selectedNode?.id ?? 'critical-path';

  return (
    <div className="blast-bottom-grid">
      <div key={remountKey} className="blast-lineage-card fade-in">
        <div className="blast-lineage-header">
          <span className="prefix">
            {selectedNode ? 'Selected node —' : 'Critical path —'}
          </span>
          <strong>{title}</strong>
        </div>

        {rows.length === 0 ? (
          <p className="li-empty">
            Click any node in the graph to inspect its source record.
          </p>
        ) : (
          <div className="blast-rows">
            {rows.map((row, i) => (
              <div key={`${row.table}-${row.field}-${i}`} className="blast-row">
                <div className="blast-row-top">
                  <span className="blast-tag">{row.table} · {row.field}</span>
                  <span className="blast-val">{row.value}</span>
                </div>
                <span className="blast-desc">{row.description}</span>
                {row.key && <span className="blast-key">{row.key}</span>}
              </div>
            ))}
          </div>
        )}

        {derivation && <p className="li-derivation">{derivation}</p>}
      </div>

      <div className="blast-callout-card">
        {selectedNode ? (
          <div className="blast-callout-body">
            <div className="blast-callout-title">Source record</div>
            <p className="blast-record-line">
              SAP table <span className="blast-mono">{selectedNode.sap_table || '—'}</span>
            </p>
            {selectedNode.sap_fields &&
              Object.entries(selectedNode.sap_fields).map(([k, v]) => (
                <div key={k} className="blast-field-row">
                  <span className="blast-field-key">{k}</span>
                  <span className="blast-field-val">{String(v)}</span>
                </div>
              ))}
            {typeof selectedNode.exposure === 'number' && selectedNode.exposure > 0 && (
              <p className="blast-record-line" style={{ marginTop: 8 }}>
                Exposure carried by this node:{' '}
                <strong>${Math.round(selectedNode.exposure).toLocaleString()}</strong>
              </p>
            )}
          </div>
        ) : (
          <>
            <div className="blast-callout-dot" />
            <div className="blast-callout-body">
              <div className="blast-callout-title">
                Click any node to inspect its source record
              </div>
              <p className="blast-callout-text">
                The lineage panel updates in place — this is how the deterministic
                engine proves its numbers rather than asserting them.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
