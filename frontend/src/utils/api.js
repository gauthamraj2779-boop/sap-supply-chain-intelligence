const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ─── Mock Data (used when backend is offline) ──────────────────────────────

export const MOCK_IMPACT_REPORT = {
  supplier: { id: 'SUP-1000', name: 'Apex Microelectronics', country: 'TW', risk_score: 0.87 },
  delay_days: 14,
  financial_summary: {
    total_exposure: 53600000,
    po_stranded_value: 2400000,
    production_halt_cost: 1440000,
    revenue_at_risk: 47200000,
    penalty_exposure: 3800000,
    residual_exposure: 2100000,
    risk_mitigated_pct: 96.1,
  },
  affected_counts: {
    purchase_orders: 12,
    materials: 8,
    plants: 5,
    production_orders: 23,
    customer_deliveries: 47,
  },
  time_to_impact_days: 8,
  blast_radius: {
    nodes: [
      { data: { id: 'sup-1000', label: 'Apex Micro\n(Supplier)', type: 'Supplier', exposure: 53600000, sap_table: 'LFA1', sap_fields: { LIFNR: '1000', NAME1: 'Apex Microelectronics', LAND1: 'TW' } } },
      { data: { id: 'mat-mcu32', label: 'MCU-32\n(Material)', type: 'Material', exposure: 38000000, sap_table: 'MARA/MARD', sap_fields: { MATNR: 'MCU-32', MAKTX: 'Microcontroller Unit 32', LABST: 850 } } },
      { data: { id: 'po-4500012', label: 'PO 4500012\n($2.4M)', type: 'PurchaseOrder', exposure: 2400000, sap_table: 'EKKO/EKPO', sap_fields: { EBELN: '4500012', NETWR: 2400000, STATUS: 'Open' } } },
      { data: { id: 'pl-1010', label: 'Plant 1010\nGermany', type: 'Plant', exposure: 18000000, sap_table: 'T001W', sap_fields: { WERKS: '1010', NAME1: 'Hamburg Plant', LAND1: 'DE' } } },
      { data: { id: 'pl-1020', label: 'Plant 1020\nSingapore', type: 'Plant', exposure: 12000000, sap_table: 'T001W', sap_fields: { WERKS: '1020', NAME1: 'Singapore Hub', LAND1: 'SG' } } },
      { data: { id: 'prod-9001', label: 'Prod Order\n#9001 (Boeing)', type: 'ProductionOrder', exposure: 31200000, sap_table: 'AFKO', sap_fields: { AUFNR: '9001', GLTRP: '2026-09-23', GAMNG: 2000 } } },
      { data: { id: 'prod-9003', label: 'Prod Order\n#9003', type: 'ProductionOrder', exposure: 8700000, sap_table: 'AFKO', sap_fields: { AUFNR: '9003', GLTRP: '2026-09-28', GAMNG: 1500 } } },
      { data: { id: 'so-4502', label: 'Sales Order\n#4502 Boeing', type: 'SalesOrder', exposure: 31200000, sap_table: 'VBAK/VBAP', sap_fields: { VBELN: '4502', NETWR: 31200000, KUNNR: 'CUS-BOEING' } } },
      { data: { id: 'so-4508', label: 'Sales Order\n#4508 Airbus', type: 'SalesOrder', exposure: 18700000, sap_table: 'VBAK/VBAP', sap_fields: { VBELN: '4508', NETWR: 18700000, KUNNR: 'CUS-AIRBUS' } } },
      { data: { id: 'del-7801', label: 'Delivery\n#7801 (Late)', type: 'Delivery', exposure: 3800000, severity: 'critical', sap_table: 'LIKP', sap_fields: { VBELN: '7801', LFDAT: '2026-09-23', LFIMG: 2000 } } },
      { data: { id: 'cus-boeing', label: 'Boeing', type: 'Customer', exposure: 31200000, sap_table: 'KNA1', sap_fields: { KUNNR: 'BOEING', NAME1: 'Boeing Company', LAND1: 'US' } } },
      { data: { id: 'cus-airbus', label: 'Airbus', type: 'Customer', exposure: 18700000, sap_table: 'KNA1', sap_fields: { KUNNR: 'AIRBUS', NAME1: 'Airbus SE', LAND1: 'DE' } } },
    ],
    edges: [
      { data: { id: 'e1', source: 'sup-1000', target: 'po-4500012', label: 'FULFILLS', severity: 'critical' } },
      { data: { id: 'e2', source: 'po-4500012', target: 'mat-mcu32', label: 'ORDERS', severity: 'critical' } },
      { data: { id: 'e3', source: 'mat-mcu32', target: 'pl-1010', label: 'STOCKED_AT', severity: 'high' } },
      { data: { id: 'e4', source: 'mat-mcu32', target: 'pl-1020', label: 'STOCKED_AT', severity: 'medium' } },
      { data: { id: 'e5', source: 'pl-1010', target: 'prod-9001', label: 'RUNS_AT', severity: 'critical' } },
      { data: { id: 'e6', source: 'pl-1010', target: 'prod-9003', label: 'RUNS_AT', severity: 'high' } },
      { data: { id: 'e7', source: 'prod-9001', target: 'so-4502', label: 'FULFILLS', severity: 'critical' } },
      { data: { id: 'e8', source: 'prod-9003', target: 'so-4508', label: 'FULFILLS', severity: 'high' } },
      { data: { id: 'e9', source: 'so-4502', target: 'del-7801', label: 'SHIPS_VIA', severity: 'critical' } },
      { data: { id: 'e10', source: 'del-7801', target: 'cus-boeing', label: 'SHIPS_TO', severity: 'critical' } },
      { data: { id: 'e11', source: 'so-4508', target: 'cus-airbus', label: 'SOLD_TO', severity: 'high' } },
    ],
  },
  avoidance_plan: {
    actions: [
      {
        id: 'act-1',
        type: 'resourcing',
        title: 'Re-source from Nova Components (Germany)',
        description: 'Re-source 1,200 units from Nova Components GmbH. Stock available, lead time 4 days vs 14-day delay.',
        cost: 12000,
        risk_mitigated: 31200000,
        roi: 2600,
        lead_time_days: 4,
        units: 1200,
        sap_table: 'EINA/EINE',
        status: 'recommended',
      },
      {
        id: 'act-2',
        type: 'safety_stock',
        title: 'Deploy Safety Stock from Plant 1020 (Singapore)',
        description: 'Transfer 800 units from Singapore hub. Covers 6 additional days of production.',
        cost: 4200,
        risk_mitigated: 18700000,
        roi: 4452,
        lead_time_days: 2,
        units: 800,
        sap_table: 'MARD',
        status: 'recommended',
      },
      {
        id: 'act-3',
        type: 'resequencing',
        title: 'Re-sequence Production Order #9003 → #9001',
        description: 'Delay non-critical Order #9003 by 3 days. Prioritize Order #9001 (Boeing). No contractual penalty on #9003.',
        cost: 0,
        risk_mitigated: 3700000,
        roi: null,
        lead_time_days: 0,
        units: null,
        sap_table: 'AFKO',
        status: 'optional',
      },
    ],
    total_avoidance_cost: 16200,
    total_risk_mitigated: 53500000,
    residual_exposure: 2100000,
    overall_roi: 3309,
  },
  confidence: {
    score: 92,
    data_completeness: 96,
    traversal_coverage: 89,
    engine_agreement: 100,
    hops_complete: 8,
    hops_total: 8,
    flags: [],
  },
  impact_timeline: [
    { day: 0, event: 'Supplier delay announced', entity: 'Apex Microelectronics', cumulative_exposure: 2400000, type: 'trigger' },
    { day: 3, event: 'PO schedule line breached', entity: 'PO #4500012', cumulative_exposure: 3840000, type: 'po' },
    { day: 6, event: 'Material stock depleted at Plant 1010', entity: 'MCU-32 @ Plant 1010', cumulative_exposure: 18000000, type: 'material' },
    { day: 8, event: 'Production Order #9001 halted', entity: 'Prod Order #9001 (Boeing)', cumulative_exposure: 31200000, type: 'production' },
    { day: 12, event: 'Sales Order #4502 delivery missed', entity: 'Boeing Order #4502', cumulative_exposure: 47200000, type: 'sales' },
    { day: 14, event: 'Customer penalty triggered', entity: 'Boeing — $3.8M penalty clause', cumulative_exposure: 53600000, type: 'penalty' },
  ],
  lineage: [
    { table: 'LFA1', field: 'LIFNR', value: "'1000'", description: 'Apex Microelectronics — Vendor Master' },
    { table: 'EKPO', field: 'EBELN/EBELP', value: "'4500012' / '10'", description: 'PO Line — $240K' },
    { table: 'EKET', field: 'EINDT', value: "'2026-09-15'", description: 'Original Delivery: Sep 15' },
    { table: 'RESB', field: 'BDMNG', value: '2000 units', description: 'Required by Prod Order #9001' },
    { table: 'MARD', field: 'LABST', value: '850 units', description: 'Current Stock at Plant 1010' },
    { table: 'CALC', field: 'SHORTFALL', value: '1,150 units × $120/unit', description: 'Shortfall = $138,000' },
  ],
  narrative: `A 14-day delay from Apex Microelectronics (Taiwan) triggers an 8-hop cascade across your supply chain. The MCU-32 component is sole-sourced, leaving Plant 1010 (Hamburg) with only 850 units against a 2,000-unit requirement — an 8-day coverage gap. Boeing's Order #4502 ($31.2M) is the highest-priority exposure. Three avoidance actions can reduce total exposure from $53.6M to $2.1M at a cost of just $16.2K — a 3,309x ROI.`,
};

// ─── Supplier Suggestions ──────────────────────────────────────────────────

export const SUPPLIER_SUGGESTIONS = [
  { id: 'SUP-1000', name: 'Apex Microelectronics', country: 'Taiwan' },
  { id: 'SUP-1001', name: 'Nova Components GmbH', country: 'Germany' },
  { id: 'SUP-1002', name: 'Pacific Semiconductor', country: 'South Korea' },
  { id: 'SUP-1003', name: 'Volta Electronics', country: 'Japan' },
  { id: 'SUP-1004', name: 'Atlas Supply Co.', country: 'USA' },
];

export const EXAMPLE_QUERIES = [
  'Supplier Apex Microelectronics is delayed by 14 days. What\'s our exposure?',
  'What if we lose our sole source for MCU-32 microcontrollers?',
  'Show me all customers affected if Plant 1010 goes offline for a week.',
  'Nova Components has a 7-day delay — impact on Boeing deliveries?',
];

// ─── API Fetch Helpers ─────────────────────────────────────────────────────

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function checkHealth() {
  return fetchJSON('/api/health');
}

export async function queryNaturalLanguage(query) {
  return fetchJSON('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export async function getImpactReport(supplierId, delayDays) {
  return fetchJSON('/api/impact', {
    method: 'POST',
    body: JSON.stringify({ supplier_id: supplierId, delay_days: delayDays }),
  });
}

// ─── Mock API (fallback) ───────────────────────────────────────────────────

export async function getMockImpactReport(supplierId, delayDays, query = '') {
  // Simulate network latency
  await new Promise(r => setTimeout(r, 1800));
  return {
    ...MOCK_IMPACT_REPORT,
    supplier: SUPPLIER_SUGGESTIONS.find(s => s.id === supplierId) || MOCK_IMPACT_REPORT.supplier,
    delay_days: delayDays || MOCK_IMPACT_REPORT.delay_days,
    query,
  };
}
