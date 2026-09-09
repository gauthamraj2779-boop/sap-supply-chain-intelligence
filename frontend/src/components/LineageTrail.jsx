import { motion, AnimatePresence } from 'framer-motion';

// Mock deterministic SAP table lookup if a node lacks explicit lineage
const NODE_SAP_DEFAULTS = {
  Supplier: {
    table: 'LFA1',
    fields: [
      { table: 'LFA1', field: 'LIFNR', value: "'1000'", description: 'Vendor master, primary key' },
      { table: 'LFA1', field: 'NAME1', value: "'Apex Microelectronics'", description: 'Vendor account name' },
      { table: 'LFM1', field: 'EKORG', value: "'1000'", description: 'Purchasing organization link' },
    ],
  },
  PurchaseOrder: {
    table: 'EKKO / EKPO',
    fields: [
      { table: 'EKKO', field: 'EBELN', value: "'4500-12'", description: 'Purchase order document number' },
      { table: 'EKPO', field: 'EBELP', value: "'00010'", description: 'PO schedule line item' },
      { table: 'EKPO', field: 'NETWR', value: '$2,400,000', description: 'Open commitment net value' },
    ],
  },
  Material: {
    table: 'MARA / MARC',
    fields: [
      { table: 'MARA', field: 'MATNR', value: "'MCU-32'", description: 'Material master record' },
      { table: 'MARC', field: 'WERKS', value: "'1010'", description: 'Plant data for material' },
      { table: 'MARD', field: 'LABST', value: '850 EA', description: 'Unrestricted stock on hand' },
    ],
  },
  Plant: {
    table: 'T001W',
    fields: [
      { table: 'T001W', field: 'WERKS', value: "'1010'", description: 'Plant Hamburg primary key' },
      { table: 'MARC', field: 'MINBE', value: '2,000 EA', description: 'Reorder threshold level' },
    ],
  },
  ProductionOrder: {
    table: 'AFKO / AFPO',
    fields: [
      { table: 'AFKO', field: 'AUFNR', value: "'9001'", description: 'Order header data PP orders' },
      { table: 'AFPO', field: 'GAMNG', value: '1,200 EA', description: 'Total order quantity' },
      { table: 'AFKO', field: 'GLTRP', value: '2026-09-24', description: 'Scheduled completion date' },
    ],
  },
  SalesOrder: {
    table: 'VBAK / VBAP',
    fields: [
      { table: 'VBAK', field: 'VBELN', value: "'4502'", description: 'Sales document header' },
      { table: 'VBAP', field: 'NETWR', value: '$31,200,000', description: 'Net sales order commitment' },
      { table: 'VBAK', field: 'KUNNR', value: "'CUST-BOEING'", description: 'Sold-to party account' },
    ],
  },
  Delivery: {
    table: 'LIKP / LIPS',
    fields: [
      { table: 'LIKP', field: 'VBELN', value: "'80014'", description: 'Outbound delivery document' },
      { table: 'LIKP', field: 'LFDAT', value: '2026-10-02', description: 'Requested delivery date' },
    ],
  },
  Customer: {
    table: 'KNA1',
    fields: [
      { table: 'KNA1', field: 'KUNNR', value: "'100045'", description: 'Customer master primary key' },
      { table: 'KNA1', field: 'NAME1', value: "'Boeing Defense & Space'", description: 'Account commercial entity' },
      { table: 'KNVV', field: 'KDGRP', value: "'Tier-1 AOG'", description: 'Customer penalty tier' },
    ],
  },
};

export default function LineageTrail({ selectedNode, defaultLineage }) {
  const nodeType = selectedNode?.type || 'Supplier';
  const nodeTitle = selectedNode
    ? (selectedNode.label || '').replace('\n', ' — ').split('(')[0].trim()
    : 'Apex Microelectronics';

  const nodeKey = selectedNode?.id || 'default-supplier';

  // Extract lineage rows: prefer explicit node lineage, then node defaults, then defaultLineage
  const lineage = selectedNode?.lineage || NODE_SAP_DEFAULTS[nodeType]?.fields || defaultLineage;
  const sapTable = selectedNode?.sap_table || NODE_SAP_DEFAULTS[nodeType]?.table || 'LFA1';

  return (
    <div className="lineage-inspector">
      {/* Key-based remount with AnimatePresence for smooth cross-fade */}
      <AnimatePresence mode="wait">
        <motion.div
          key={nodeKey}
          className="li-inner-wrap"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, width: '100%' }}
        >
          {/* Left: SAP lineage trail */}
          <div className="li-left">
            <div className="li-title">
              Selected node — <span style={{ color: 'var(--ink)' }}>{nodeTitle}</span>
            </div>
            {!lineage || lineage.length === 0 ? (
              <p className="li-empty">Click any node in the graph to inspect its source record.</p>
            ) : (
              <div className="li-trail">
                {lineage.map((step, i) => (
                  <motion.div
                    key={`${step.table}-${step.field}-${i}`}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05, duration: 0.2 }}
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
            )}
          </div>

          {/* Right: prompt or deterministic proof info */}
          <div className="li-right">
            <div className="li-title">Deterministic proof inspector</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
                <strong>{(selectedNode?.label || 'Apex Microelectronics (Taiwan)').replace('\n', ' ')}</strong>
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Primary SAP table:</span>
                <span className="ltr-table" style={{ fontSize: 11, padding: '2px 6px', background: 'var(--paper-2)', borderRadius: 2 }}>
                  {sapTable}
                </span>
              </div>

              {selectedNode?.sap_fields ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                  {Object.entries(selectedNode.sap_fields).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', gap: 8, fontSize: 12, fontFamily: 'var(--mono)' }}>
                      <span style={{ color: 'var(--ink-4)', minWidth: 64 }}>{k}</span>
                      <span style={{ color: 'var(--ink)' }}>{String(v)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="li-empty" style={{ margin: 0 }}>
                  The lineage panel updates in place on node tap — verifying deterministic proof directly against ERP tables.
                </p>
              )}
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
