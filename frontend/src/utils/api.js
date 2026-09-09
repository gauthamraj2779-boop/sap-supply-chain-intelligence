/**
 * API client for the SAP Knowledge Graph backend.
 *
 * There is no mock data and no offline fallback anywhere in this file. Every
 * number rendered by the console comes from a live call to the backend; if the
 * backend is unreachable the UI says so rather than showing invented figures.
 *
 * The backend's ImpactReport is richer than the view needs, so `adaptReport`
 * reshapes it for the components. It only ever re-keys and re-groups values —
 * it never computes a figure. Financial ratios (ROI, mitigation %) are
 * serialized by the backend for exactly this reason.
 */

const BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, { status = 0, detail = null, cause = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.cause = cause;
  }
}

async function request(path, { method = 'GET', body, timeout = 60000 } = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeout),
    });
  } catch (err) {
    throw new ApiError(
      `Cannot reach the analysis backend at ${BASE_URL}. Start it with ` +
        `\`cd backend && make run\`.`,
      { cause: err },
    );
  }

  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json())?.detail ?? null;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail || `Backend returned ${res.status} ${res.statusText}`, {
      status: res.status,
      detail,
    });
  }
  return res.json();
}

// ─── Endpoints ─────────────────────────────────────────────────────────────

export const checkHealth = () => request('/api/health', { timeout: 5000 });
export const getSuppliers = () => request('/api/suppliers');
export const getExampleQueries = () => request('/api/query/examples');
export const getValidationReport = () => request('/api/validation');
export const getGraphSchema = () => request('/api/schema');

export const runQuery = (question) =>
  request('/api/query', { method: 'POST', body: { question } });

export const runImpact = (supplier_id, delay_days, horizon_days) =>
  request('/api/impact', {
    method: 'POST',
    body: { supplier_id, delay_days, ...(horizon_days ? { horizon_days } : {}) },
  });

// ─── Adapter: backend ImpactReport → view model ────────────────────────────

const SEVERITY_RANK = { none: 0, low: 1, medium: 2, high: 3, critical: 4 };

const worseOf = (a = 'none', b = 'none') =>
  (SEVERITY_RANK[a] ?? 0) >= (SEVERITY_RANK[b] ?? 0) ? a : b;

/** Cytoscape needs `{ data: {...} }` elements and unique edge ids. */
function toCytoscape(nodes, edges) {
  const severityById = Object.fromEntries(nodes.map((n) => [n.id, n.severity]));

  const cyNodes = nodes.map((n) => ({
    data: {
      id: n.id,
      label: n.caption,
      type: n.label,
      severity: n.severity,
      exposure: n.exposure,
      sap_table: n.sap_table,
      sap_fields: n.sap_fields,
      lineage: n.lineage,
      ...n.properties,
    },
  }));

  const cyEdges = edges.map((e, i) => ({
    data: {
      id: `e${i}-${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      label: e.type,
      // An edge is only as safe as the more damaged end it connects.
      severity: worseOf(severityById[e.source], severityById[e.target]),
      derived_from: e.derived_from,
    },
  }));

  return { nodes: cyNodes, edges: cyEdges };
}

/** Flatten a backend LineageTrail into the table rows the inspector renders. */
function flattenLineage(trail) {
  if (!trail?.steps?.length) return [];
  return trail.steps.map((s) => ({
    table: s.sap_table,
    field: s.sap_field,
    value: s.value,
    description: s.meaning,
    key: s.key,
  }));
}

export function adaptReport(report) {
  const fe = report.financial_exposure;
  const plan = report.avoidance;
  const t = report.traversal;

  return {
    supplier: report.supplier,
    delay_days: report.delay_days,
    as_of_date: report.as_of_date,
    headline: report.headline,
    warnings: report.warnings ?? [],

    narrative: {
      text: report.narrative,
      source: report.narrative_source,
      // True only when a language model actually wrote it. The console labels
      // the two cases differently rather than passing one off as the other.
      is_llm: Boolean(report.narrative),
    },

    financial_summary: {
      total_exposure: fe.total_financial_exposure,
      po_stranded_value: fe.po_stranded_value,
      production_halt_cost: fe.production_halt_cost,
      revenue_at_risk: fe.revenue_at_risk,
      penalty_exposure: fe.penalty_exposure,
      residual_exposure: plan ? plan.exposure_after : fe.total_financial_exposure,
      risk_mitigated_pct: plan ? plan.mitigation_pct * 100 : 0,
      components_reconcile: fe.components_reconcile,
      assumptions: fe.assumptions ?? [],
    },

    customers: fe.by_customer ?? [],
    affected_counts: report.affected_counts,
    time_to_impact_days: report.time_to_impact_days,

    blast_radius: toCytoscape(report.blast_radius_nodes, report.blast_radius_edges),

    avoidance_plan: plan
      ? {
          actions: plan.actions.map((a, i) => ({
            id: `${a.kind}-${a.target_matnr ?? i}-${i}`,
            type: a.kind,
            title: a.title,
            description: a.description,
            cost: a.cost,
            risk_mitigated: a.risk_mitigated,
            roi: a.roi,
            roi_display: a.roi_display,
            lead_time_days: a.lead_time_days,
            units: a.qty_covered,
            sap_table: a.sap_source,
            evidence: a.evidence ?? [],
          })),
          rejected: plan.considered_but_rejected ?? [],
          total_avoidance_cost: plan.total_avoidance_cost,
          total_risk_mitigated: plan.total_risk_mitigated,
          residual_exposure: plan.exposure_after,
          exposure_before: plan.exposure_before,
          overall_roi: plan.plan_roi,
          mitigation_pct: plan.mitigation_pct * 100,
        }
      : null,

    confidence: {
      score: Math.round(report.confidence.overall * 100),
      data_completeness: Math.round(report.confidence.data_completeness * 100),
      traversal_coverage: Math.round(report.confidence.traversal_coverage * 100),
      engine_agreement: Math.round(report.confidence.engine_agreement * 100),
      hops_complete: t.hops_completed.length,
      hops_total: t.hops_completed.length + t.hops_failed.length,
      degraded_modes: report.confidence.degraded_modes ?? [],
      notes: report.confidence.notes ?? [],
      formula: report.confidence.formula,
    },

    impact_timeline: (report.timeline ?? []).map((e) => ({
      day: e.day_offset,
      date: e.event_date,
      event: e.label,
      detail: e.detail,
      cumulative_exposure: e.cumulative_exposure,
      type: e.kind,
    })),

    // The audit trail for the single largest exposure, supplier to customer.
    lineage: flattenLineage(report.critical_path),
    critical_path_subject: report.critical_path?.subject ?? null,
    critical_path_derivation: report.critical_path?.derivation ?? null,

    // Kept for the overview insights, which read real shortfall figures.
    materials: t.materials ?? [],
    production_orders: t.production_orders ?? [],
    deliveries: t.deliveries ?? [],
  };
}

/**
 * Run a natural-language question end to end.
 * Throws ApiError on transport failure or when the question names no supplier.
 */
export async function analyseQuestion(question) {
  const result = await runQuery(question);
  if (!result.report) {
    throw new ApiError(result.error || 'The question could not be interpreted.', {
      detail: result.interpreted,
    });
  }
  return { view: adaptReport(result.report), interpreted: result.interpreted };
}
