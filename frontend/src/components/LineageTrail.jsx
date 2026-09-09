import { motion } from 'framer-motion';

// Deterministic ERP lookup records matching the reference mockup and SAP tables
const NODE_LINEAGE_MAP = {
  'sup-apex': {
    title: 'Apex Microelectronics',
    rows: [
      { table: 'LFA1', field: 'LIFNR', value: "'1000'", description: 'Vendor master, primary key' },
      { table: 'EKPO', field: 'EBELN', value: "'4500012' / line 10", description: 'PO line, value $240K' },
      { table: 'EKET', field: 'EINDT', value: '2026-09-15', description: 'Original scheduled delivery' },
      { table: 'RESB', field: 'BDMNG', value: '2,000 units', description: 'Required by production order #9001' },
      { table: 'MARD', field: 'LABST', value: '850 units', description: 'Current stock, Plant 1010' },
    ],
  },
  'po-4500': {
    title: 'PO #4500-12',
    rows: [
      { table: 'EKKO', field: 'EBELN', value: "'4500012'", description: 'Purchasing document header' },
      { table: 'EKPO', field: 'EBELP', value: "'00010'", description: 'PO line item for MCU-32 procurement' },
      { table: 'EKPO', field: 'NETWR', value: '$2,400,000', description: 'Net open commitment value' },
      { table: 'EKET', field: 'EINDT', value: '2026-09-15', description: 'Promised delivery schedule date' },
      { table: 'EKES', field: 'EBELP', value: 'Overdue (+14d)', description: 'Schedule line breach status' },
    ],
  },
  'mat-mcu32': {
    title: 'MCU-32',
    rows: [
      { table: 'MARA', field: 'MATNR', value: "'MCU-32'", description: 'Material master, 32-bit automotive microcontroller' },
      { table: 'MARC', field: 'WERKS', value: "'1010'", description: 'Plant Hamburg data for material' },
      { table: 'MARD', field: 'LABST', value: '850 units', description: 'Current stock, Plant 1010' },
      { table: 'RESB', field: 'BDMNG', value: '2,000 units', description: 'Required by production order #9001' },
      { table: 'MARC', field: 'MINBE', value: '1,500 units', description: 'Safety stock threshold' },
    ],
  },
  'pl-1010': {
    title: 'Plant 1010, Hamburg',
    rows: [
      { table: 'T001W', field: 'WERKS', value: "'1010'", description: 'Plant Hamburg primary key' },
      { table: 'T001K', field: 'BUKRS', value: "'1000'", description: 'Company code Germany manufacturing hub' },
      { table: 'AFKO', field: 'AUFNR', value: "'9001'", description: 'PP order scheduled at work center' },
      { table: 'MARD', field: 'LABST', value: '850 units', description: 'Physical stock on site (depletion Day 6)' },
      { table: 'CRHD', field: 'ARBPL', value: "'LINE-03'", description: 'Assembly line affected by MCU shortage' },
    ],
  },
  'prod-9001': {
    title: 'Prod. order #9001',
    rows: [
      { table: 'AFKO', field: 'AUFNR', value: "'9001'", description: 'Production order header' },
      { table: 'AFPO', field: 'MATNR', value: "'MCU-32'", description: 'Component input requirement' },
      { table: 'AFPO', field: 'GAMNG', value: '2,000 units', description: 'Target assembly output batch' },
      { table: 'AFKO', field: 'GLTRP', value: '2026-09-24', description: 'Scheduled finish date for Boeing delivery' },
      { table: 'AFKO', field: 'DISPO', value: "'PP-01'", description: 'MRP controller priority flag' },
    ],
  },
  'so-4502': {
    title: 'Sales order #4502',
    rows: [
      { table: 'VBAK', field: 'VBELN', value: "'4502'", description: 'Sales document header commitment' },
      { table: 'VBAP', field: 'POSNR', value: "'000010'", description: 'Line item commitment: 1,500 flight computers' },
      { table: 'VBAP', field: 'NETWR', value: '$31,200,000', description: 'Net sales order commitment value' },
      { table: 'VBAK', field: 'KUNNR', value: "'100045'", description: 'Sold-to party: Boeing Commercial' },
      { table: 'VBKD', field: 'INCO1', value: "'FOB'", description: 'Incoterms delivery condition Frankfurt' },
    ],
  },
  'cus-boeing': {
    title: 'Boeing',
    rows: [
      { table: 'KNA1', field: 'KUNNR', value: "'100045'", description: 'Customer master primary key' },
      { table: 'KNA1', field: 'NAME1', value: "'Boeing Defense & Space'", description: 'Customer commercial entity' },
      { table: 'KNVV', field: 'KDGRP', value: "'Tier-1 AOG'", description: 'Penalty clause: $3.8M on delivery breach' },
      { table: 'LIKP', field: 'VBELN', value: "'80014'", description: 'Outbound delivery scheduled 2026-10-02' },
      { table: 'VBAK', field: 'NETWR', value: '$31,200,000', description: 'Largest single revenue exposure in cycle' },
    ],
  },
  'so-4508': {
    title: 'Sales order #4508',
    rows: [
      { table: 'VBAK', field: 'VBELN', value: "'4508'", description: 'Sales document header commitment' },
      { table: 'VBAP', field: 'POSNR', value: "'000020'", description: 'Line item commitment: 900 cockpit avionics' },
      { table: 'VBAP', field: 'NETWR', value: '$18,700,000', description: 'Net sales order commitment value' },
      { table: 'VBAK', field: 'KUNNR', value: "'100092'", description: 'Sold-to party: Airbus SE Toulouse' },
      { table: 'VBKD', field: 'INCO1', value: "'CIF'", description: 'Incoterms delivery destination Toulouse' },
    ],
  },
  'cus-airbus': {
    title: 'Airbus',
    rows: [
      { table: 'KNA1', field: 'KUNNR', value: "'100092'", description: 'Customer master primary key' },
      { table: 'KNA1', field: 'NAME1', value: "'Airbus SE'", description: 'Customer commercial entity' },
      { table: 'KNVV', field: 'KDGRP', value: "'Strategic Commercial'", description: 'Priority SLA contract agreement' },
      { table: 'VBAK', field: 'NETWR', value: '$18,700,000', description: 'Second largest revenue commitment at risk' },
      { table: 'LIKP', field: 'VBELN', value: "'80019'", description: 'Outbound delivery schedule line' },
    ],
  },
  'gap': {
    title: 'Coverage gap',
    rows: [
      { table: 'GAP', field: 'TYPE', value: "'Sole Source'", description: 'No second approved supplier on file at Plant 1010' },
      { table: 'GAP', field: 'DURATION', value: '8 days', description: 'Production halt window between depletion and restock' },
      { table: 'GAP', field: 'DEFICIT', value: '1,150 units', description: 'Unmet MCU-32 demand across active runs' },
      { table: 'GAP', field: 'EXPOSURE', value: '$53,600,000', description: 'Total cascading financial exposure' },
    ],
  },
};

export default function LineageTrail({ selectedNodeId = 'sup-apex' }) {
  const currentId = selectedNodeId || 'sup-apex';
  const data = NODE_LINEAGE_MAP[currentId] || NODE_LINEAGE_MAP['sup-apex'];

  return (
    <div className="blast-bottom-grid">
      {/* Left card: selected node lineage rows with key-based remount for CSS cross-fade */}
      <div key={currentId} className="blast-lineage-card fade-in">
        <div className="blast-lineage-header">
          <span className="prefix">Selected node —</span>
          <strong>{data.title}</strong>
        </div>
        <div className="blast-rows">
          {data.rows.map((row, i) => (
            <div key={`${row.table}-${row.field}-${i}`} className="blast-row">
              <div className="blast-row-top">
                <span className="blast-tag">{row.table} · {row.field}</span>
                <span className="blast-val">{row.value}</span>
              </div>
              <span className="blast-desc">{row.description}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right card: callout prompt */}
      <div className="blast-callout-card">
        <div className="blast-callout-dot" />
        <div className="blast-callout-body">
          <div className="blast-callout-title">Click any node to inspect its source record</div>
          <p className="blast-callout-text">
            The lineage panel updates in place — this is how the deterministic engine proves its numbers rather than asserting them.
          </p>
        </div>
      </div>
    </div>
  );
}
