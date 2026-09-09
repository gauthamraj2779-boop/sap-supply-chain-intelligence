"""The agent's tool surface.

Each tool is a thin wrapper over code that already exists and is already
tested. Nothing here computes a business figure of its own: ``supplier_delay_impact``
delegates to ``engines.orchestrator.analyse`` unchanged, so cross-checking, the
confidence score and the declared assumptions all still apply to anything the
agent says about money.

Two rules shape the return values:

* **Small.** Tool output is fed back into the model's context, so rows are
  capped and trimmed to the fields that answer the question. The untrimmed
  ImpactReport rides alongside on ``ToolResult.report`` for the HTTP response.
* **Attributed.** Every handler declares the SAP tables it actually read. That
  list is what the trajectory shows -- never the model's claim about it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.engines.deterministic import DEFAULT_HORIZON_DAYS, SupplierNotFound
from app.engines.orchestrator import analyse
from app.graph.adapter import GraphBackend, GraphUnavailable
from app.graph.schema import BLAST_RADIUS_HOPS, EDGE_TYPES, NODE_TYPES
from app.models import ImpactReport

logger = logging.getLogger(__name__)

# Rows returned to the model per tool call. Enough to reason over, small enough
# that eight steps of history still fit comfortably in a context window.
MAX_ROWS = 25


@dataclass
class ToolResult:
    """What a handler produced, plus the provenance the trajectory renders."""

    data: Any
    summary: str
    sap_tables: list[str] = field(default_factory=list)
    error: str | None = None
    # Only supplier_delay_impact sets this: the full deterministic report, so the
    # API can hand the UI its normal panels without recomputing anything.
    report: ImpactReport | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolError(Exception):
    """A handler could not answer. Reported to the model as a tool result."""


# --------------------------------------------------------------------------
# Which SAP tables each traversal hop reads. Used to attribute
# supplier_delay_impact to the tables the traversal genuinely touched rather
# than to a static list that would over-claim on a partial traversal.
# --------------------------------------------------------------------------
_HOP_TABLES: dict[str, tuple[str, ...]] = {
    "supplier": ("LFA1",),
    "purchase_orders": ("EKKO", "EKPO"),
    "schedule_lines": ("EKET",),
    "materials": ("MARA", "MARC", "MARD"),
    "plants": ("T001W",),
    "production_orders": ("AFKO", "AFPO", "RESB"),
    "sales_orders": ("VBAK", "VBAP"),
    "deliveries": ("LIKP", "LIPS"),
    "customers": ("KNA1",),
}

_WRITE_CLAUSES = (
    "create", "merge", "delete", "set", "drop", "remove", "detach",
    "load csv", "foreach", "call db.", "call apoc.",
)


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
def get_ontology_schema(backend: GraphBackend) -> ToolResult:
    """The label/edge vocabulary, so the model cannot invent node types."""
    nodes = [
        {
            "label": nt.label,
            "key": nt.key_property,
            "source_tables": list(nt.source_tables),
            "definition": nt.business_definition,
            "properties": [
                {"property": f.graph_property, "sap": f"{f.sap_table}.{f.sap_field}",
                 "business_term": f.business_term}
                for f in nt.fields
            ],
        }
        for nt in NODE_TYPES.values()
    ]
    edges = [
        {"type": e.type, "from": e.source_label, "to": e.target_label,
         "derived_from": e.derived_from, "meaning": e.business_meaning}
        for e in EDGE_TYPES
    ]
    return ToolResult(
        data={"node_types": nodes, "edge_types": edges,
              "blast_radius_hops": list(BLAST_RADIUS_HOPS)},
        summary=f"{len(nodes)} node labels, {len(edges)} edge types, "
                f"{len(BLAST_RADIUS_HOPS)} blast-radius hops",
        # Ontology metadata describes tables; it reads no records from them.
        sap_tables=[],
    )


def find_suppliers(
    backend: GraphBackend, country: str | None = None, name_contains: str | None = None
) -> ToolResult:
    """LFA1 roster, optionally filtered. The entry point for 'suppliers in X'."""
    rows = backend.suppliers()
    if country:
        want = country.strip().upper()
        rows = [r for r in rows if str(r.get("LAND1", "")).upper() == want]
    if name_contains:
        needle = name_contains.strip().lower()
        rows = [r for r in rows if needle in str(r.get("NAME1", "")).lower()]

    out = [
        {"LIFNR": r["LIFNR"], "NAME1": r.get("NAME1"), "LAND1": r.get("LAND1"),
         "ORT01": r.get("ORT01"), "risk_score": r.get("risk_score")}
        for r in rows[:MAX_ROWS]
    ]
    where = f" in {country.upper()}" if country else ""
    return ToolResult(
        data={"suppliers": out, "count": len(rows)},
        summary=(f"{len(rows)} supplier(s){where}: "
                 + ", ".join(f"{r['NAME1']} ({r['LIFNR']})" for r in out[:5])
                 if out else f"no suppliers matched{where}"),
        sap_tables=["LFA1"],
    )


def supplier_delay_impact(
    backend: GraphBackend,
    supplier_id: str,
    delay_days: int = 14,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    shacl_report=None,
) -> ToolResult:
    """The full deterministic impact pipeline, unchanged.

    This is the only tool that produces money, and it produces it by calling the
    exact function ``/api/impact`` calls. The agent decides when to invoke it; it
    never re-derives or adjusts what comes back.
    """
    try:
        delay = max(1, int(delay_days))
    except (TypeError, ValueError):
        delay = 14
    try:
        horizon = max(int(horizon_days), delay + 1)
    except (TypeError, ValueError):
        horizon = max(DEFAULT_HORIZON_DAYS, delay + 1)

    try:
        report = analyse(
            backend, supplier_id=str(supplier_id).strip(), delay_days=delay,
            horizon_days=horizon,
            # The agent writes the final prose itself, so the narrator inside the
            # pipeline is skipped: one LLM voice per answer, not two.
            include_narrative=False,
            shacl_report=shacl_report,
        )
    except SupplierNotFound as exc:
        raise ToolError(
            f"{exc}. Call find_suppliers to see the valid LIFNR values."
        ) from exc

    fe = report.financial_exposure
    t = report.traversal
    digest = {
        "supplier": {"lifnr": report.supplier.lifnr, "name": report.supplier.name,
                     "country": report.supplier.country,
                     "sole_source_materials": report.supplier.sole_source_materials},
        "delay_days": report.delay_days,
        "headline": report.headline,
        "time_to_impact_days": report.time_to_impact_days,
        "financial_exposure": {
            "total": fe.total_financial_exposure,
            "po_stranded_value": fe.po_stranded_value,
            "production_halt_cost": fe.production_halt_cost,
            "revenue_at_risk": fe.revenue_at_risk,
            "penalty_exposure": fe.penalty_exposure,
        },
        "affected_counts": report.affected_counts.model_dump(),
        "customers_at_risk": [
            {"kunnr": c.kunnr, "name": c.customer_name,
             "total_exposure": c.total_exposure,
             "deliveries_at_risk": c.deliveries_at_risk}
            for c in fe.by_customer[:MAX_ROWS]
        ],
        "materials_short": [
            {"matnr": m.matnr, "werks": m.werks, "shortfall_qty": m.shortfall_qty,
             "on_hand_qty": m.on_hand_qty, "required_qty": m.required_qty,
             "stockout_date": m.stockout_date.isoformat() if m.stockout_date else None,
             "severity": m.severity}
            for m in t.materials if m.shortfall_qty > 0
        ][:MAX_ROWS],
        "production_orders_halted": [
            {"aufnr": p.aufnr, "output_matnr": p.output_matnr, "werks": p.werks,
             "halt_days": p.halt_days}
            for p in t.production_orders
        ][:MAX_ROWS],
        "avoidance": (
            {"actions": [{"title": a.title, "cost": a.cost,
                          "risk_mitigated": a.risk_mitigated}
                         for a in report.avoidance.actions[:MAX_ROWS]],
             "total_cost": report.avoidance.total_avoidance_cost,
             "exposure_after": report.avoidance.exposure_after,
             "mitigation_pct": report.avoidance.mitigation_pct}
            if report.avoidance else None
        ),
        "confidence": round(report.confidence.overall, 4),
        "warnings": report.warnings,
        "note": ("These figures are computed deterministically. Quote them exactly; "
                 "do not recompute, rescale or round them differently."),
    }

    tables: list[str] = []
    for hop in t.hops_completed:
        for tbl in _HOP_TABLES.get(hop, ()):
            if tbl not in tables:
                tables.append(tbl)

    return ToolResult(
        data=digest,
        summary=(f"{report.supplier.name} +{report.delay_days}d: "
                 f"{fe.total_financial_exposure:,.0f} USD exposure across "
                 f"{report.affected_counts.customers} customer(s), "
                 f"{report.affected_counts.deliveries} delivery(ies); "
                 f"{len(t.hops_completed)} hops traversed"),
        sap_tables=tables,
        report=report,
    )


def find_material_stock(
    backend: GraphBackend, matnr: str, werks: str | None = None
) -> ToolResult:
    """MARD unrestricted stock and MARC planning data, one plant or all."""
    matnr = str(matnr).strip()
    master = backend.material(matnr)
    if master is None:
        raise ToolError(f"No material with MATNR={matnr} in MARA.")

    if werks:
        row = backend.stock(matnr, str(werks).strip())
        if row is None:
            raise ToolError(f"No MARD record for MATNR={matnr} at WERKS={werks}.")
        rows = [row]
    else:
        rows = backend.stock_all_plants(matnr)

    total = sum(float(r.get("LABST", 0.0)) for r in rows)
    return ToolResult(
        data={"matnr": matnr, "material_name": master.get("MAKTX", ""),
              "stock": rows[:MAX_ROWS], "plants": len(rows), "total_on_hand": total},
        summary=(f"{matnr} ({master.get('MAKTX', '')}): {total:,.0f} units on hand "
                 f"across {len(rows)} plant(s)"),
        sap_tables=["MARA", "MARC", "MARD"],
    )


def find_reservations(backend: GraphBackend, matnr: str, werks: str) -> ToolResult:
    """RESB component requirements against a material at a plant."""
    matnr, werks = str(matnr).strip(), str(werks).strip()
    rows = backend.reservations_for(matnr, werks)
    if not rows:
        return ToolResult(
            data={"matnr": matnr, "werks": werks, "reservations": [], "count": 0},
            summary=f"no RESB requirements for {matnr} at plant {werks}",
            sap_tables=["RESB"],
        )
    demand = sum(float(r["BDMNG"]) for r in rows)
    return ToolResult(
        data={"matnr": matnr, "werks": werks, "reservations": rows[:MAX_ROWS],
              "count": len(rows), "total_required_qty": demand,
              "earliest_required_date": rows[0]["BDTER"]},
        summary=(f"{len(rows)} reservation(s) for {matnr} at {werks} totalling "
                 f"{demand:,.0f} units, earliest {rows[0]['BDTER']}"),
        sap_tables=["RESB"],
    )


def trace_downstream(backend: GraphBackend, aufnr: str) -> ToolResult:
    """Production order -> sales orders -> deliveries -> customers."""
    aufnr = str(aufnr).strip()
    order = backend.production_order(aufnr)
    if order is None:
        raise ToolError(f"No production order with AUFNR={aufnr} in AFKO.")

    output = order.get("output_MATNR") or order.get("PLNBEZ")
    sales = backend.sales_items_for_material(output)

    orders_out, deliveries_out, customers = [], [], {}
    for so in sales[:MAX_ROWS]:
        orders_out.append({
            "vbeln": so["VBELN"], "posnr": so["POSNR"], "matnr": so["MATNR"],
            "kwmeng": so["KWMENG"], "netwr": so["NETWR"],
            "kunnr": so["KUNNR"], "customer_name": so["customer_name"],
        })
        customers.setdefault(so["KUNNR"], so["customer_name"])
        for dv in backend.deliveries_for_sales_order(so["VBELN"]):
            deliveries_out.append({
                "vbeln": dv["VBELN"], "ref_sales_order": dv["VGBEL"],
                "lfdat": dv["LFDAT"], "lfimg": dv["LFIMG"],
                "kunnr": dv["KUNNR"], "customer_name": dv["customer_name"],
                "penalty_rate": dv["penalty_rate"],
            })
            customers.setdefault(dv["KUNNR"], dv["customer_name"])

    return ToolResult(
        data={
            "production_order": {"aufnr": aufnr, "output_matnr": output,
                                 "werks": order["WERKS"], "gamng": order["GAMNG"],
                                 "scheduled_finish": order["GLTRP"]},
            "sales_orders": orders_out,
            "deliveries": deliveries_out[:MAX_ROWS],
            "customers": [{"kunnr": k, "name": v} for k, v in customers.items()],
            "note": ("Structural reach only. Financial exposure for these customers "
                     "comes from supplier_delay_impact, not from this tool."),
        },
        summary=(f"order {aufnr} makes {output}: {len(orders_out)} sales order(s), "
                 f"{len(deliveries_out)} delivery(ies), {len(customers)} customer(s)"),
        sap_tables=["AFKO", "AFPO", "VBAK", "VBAP", "LIKP", "LIPS", "KNA1"],
    )


def find_alternate_sources(backend: GraphBackend, matnr: str) -> ToolResult:
    """EINA/EINE approved sources for a material, cheapest lead time first."""
    matnr = str(matnr).strip()
    if backend.material(matnr) is None:
        raise ToolError(f"No material with MATNR={matnr} in MARA.")
    # exclude_lifnr="" excludes nothing: this asks for the whole source list.
    rows = backend.alternate_sources(matnr, exclude_lifnr="")
    return ToolResult(
        data={"matnr": matnr, "sources": rows[:MAX_ROWS], "count": len(rows),
              "is_sole_sourced": len(rows) <= 1},
        summary=(f"{matnr}: {len(rows)} approved source(s)"
                 + (" - sole sourced" if len(rows) <= 1 else "")),
        sap_tables=["EINA", "EINE", "LFA1"],
    )


def lineage(backend: GraphBackend, node_type: str, node_id: str) -> ToolResult:
    """SAP table/field provenance for a node type, from the schema module."""
    nt = NODE_TYPES.get(str(node_type).strip())
    if nt is None:
        raise ToolError(
            f"Unknown node type '{node_type}'. Known types: {', '.join(NODE_TYPES)}."
        )
    return ToolResult(
        data={
            "node_type": nt.label, "node_id": node_id,
            "source_tables": list(nt.source_tables),
            "definition": nt.business_definition,
            "fields": [{"sap_table": f.sap_table, "sap_field": f.sap_field,
                        "graph_property": f.graph_property,
                        "business_term": f.business_term}
                       for f in nt.fields],
        },
        summary=(f"{nt.label} {node_id} derives from "
                 f"{', '.join(nt.source_tables)} ({len(nt.fields)} mapped fields)"),
        sap_tables=list(nt.source_tables),
    )


def run_cypher(backend: GraphBackend, query: str) -> ToolResult:
    """Read-only Cypher. Neo4j backend only; writes are refused before dispatch."""
    q = str(query).strip()
    if not q:
        raise ToolError("Empty Cypher query.")

    # Refuse mutations here rather than trusting the driver or the model: the
    # graph is a read-only analytical surface for the agent, full stop.
    lowered = re.sub(r"'[^']*'|\"[^\"]*\"", "", q).lower()
    for clause in _WRITE_CLAUSES:
        # Trailing boundary only for clauses that end in a word character;
        # "call apoc." is deliberately a prefix match.
        tail = "(?![a-z0-9_])" if clause[-1].isalnum() else ""
        if re.search(rf"(?<![a-z0-9_]){re.escape(clause)}{tail}", lowered):
            raise ToolError(
                f"Refused: '{clause.upper()}' is a write or procedure clause and this "
                "tool is read-only. Use a MATCH ... RETURN query."
            )
    if "match" not in lowered and "return" not in lowered:
        raise ToolError("Refused: only MATCH ... RETURN read queries are accepted.")

    try:
        rows = backend.run_cypher(q)
    except GraphUnavailable as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:  # a malformed query is the model's problem to fix
        raise ToolError(f"Cypher failed: {exc}") from exc

    # Attribute the query to the source tables of whichever labels it names.
    tables: list[str] = []
    for label, nt in NODE_TYPES.items():
        if re.search(rf"(?<![A-Za-z0-9_]){label}(?![A-Za-z0-9_])", q):
            for tbl in nt.source_tables:
                if tbl not in tables:
                    tables.append(tbl)

    return ToolResult(
        data={"rows": rows[:MAX_ROWS], "row_count": len(rows),
              "truncated": len(rows) > MAX_ROWS, "backend": backend.name},
        summary=f"{len(rows)} row(s) from Cypher on the {backend.name} backend",
        sap_tables=tables,
    )


# --------------------------------------------------------------------------
# Wire format: OpenAI function-calling schemas
# --------------------------------------------------------------------------
# Every tool carries the same `reason` argument. It costs one sentence and buys
# the trajectory a rationale that is genuinely the model's, written before the
# call rather than reconstructed after it. It is stripped before dispatch.
_REASON = {
    "type": "string",
    "description": "One sentence: why you are making this call now.",
}


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {**properties, "reason": _REASON},
                "required": [*required, "reason"],
            },
        },
    }


TOOL_SPECS: list[dict] = [
    _spec(
        "get_ontology_schema",
        "List the graph's node labels, edge types and their SAP source tables. "
        "Call this first when you are unsure what exists; never invent a label.",
        {}, [],
    ),
    _spec(
        "find_suppliers",
        "List suppliers from LFA1, optionally filtered by country key (LAND1, e.g. "
        "'TW', 'DE', 'JP', 'US') or by a substring of the name. Use this to resolve "
        "a question about a place or a company name into LIFNR values.",
        {"country": {"type": "string", "description": "LFA1.LAND1 country key, e.g. TW"},
         "name_contains": {"type": "string", "description": "Substring of LFA1.NAME1"}},
        [],
    ),
    _spec(
        "supplier_delay_impact",
        "Run the full deterministic impact pipeline for one supplier and a delay in "
        "days. Returns computed financial exposure, affected counts, customers at "
        "risk, shortfalls and the avoidance plan. This is the ONLY source of money "
        "figures: quote what it returns verbatim and never compute your own.",
        {"supplier_id": {"type": "string", "description": "LFA1.LIFNR, exactly as listed"},
         "delay_days": {"type": "integer",
                        "description": "Delay in days. Use 14 if the question does not say."},
         "horizon_days": {"type": "integer",
                          "description": "Look-ahead window in days. Default 45."}},
        ["supplier_id", "delay_days"],
    ),
    _spec(
        "find_material_stock",
        "Unrestricted stock (MARD.LABST) and planning data (MARC) for a material, at "
        "one plant or across all plants.",
        {"matnr": {"type": "string", "description": "MARA.MATNR"},
         "werks": {"type": "string", "description": "Plant. Omit for every plant."}},
        ["matnr"],
    ),
    _spec(
        "find_reservations",
        "Component requirements (RESB) against a material at a plant: which "
        "production orders consume it, how much, and by when.",
        {"matnr": {"type": "string", "description": "MARA.MATNR"},
         "werks": {"type": "string", "description": "Plant"}},
        ["matnr", "werks"],
    ),
    _spec(
        "trace_downstream",
        "Follow a production order to the sales orders, deliveries and customers it "
        "feeds. Structural reach only, no financial figures.",
        {"aufnr": {"type": "string", "description": "AFKO.AUFNR"}},
        ["aufnr"],
    ),
    _spec(
        "find_alternate_sources",
        "Approved sources for a material from the source list (EINA/EINE), with net "
        "price and planned lead time. Use it to tell whether a material is sole-sourced.",
        {"matnr": {"type": "string", "description": "MARA.MATNR"}},
        ["matnr"],
    ),
    _spec(
        "lineage",
        "SAP table and field provenance for a node type, so an answer can cite where "
        "a value came from.",
        {"node_type": {"type": "string",
                       "description": f"One of: {', '.join(NODE_TYPES)}"},
         "node_id": {"type": "string", "description": "Key of the record, e.g. MCU-32"}},
        ["node_type", "node_id"],
    ),
    _spec(
        "run_cypher",
        "Run a read-only MATCH ... RETURN Cypher query. Available only when the "
        "Neo4j backend is configured; writes are refused. Prefer the specific tools "
        "above -- reach for this only for a shape they cannot express.",
        {"query": {"type": "string", "description": "A read-only Cypher query"}},
        ["query"],
    ),
]

TOOL_NAMES: tuple[str, ...] = tuple(s["function"]["name"] for s in TOOL_SPECS)

_HANDLERS: dict[str, Callable[..., ToolResult]] = {
    "get_ontology_schema": get_ontology_schema,
    "find_suppliers": find_suppliers,
    "supplier_delay_impact": supplier_delay_impact,
    "find_material_stock": find_material_stock,
    "find_reservations": find_reservations,
    "trace_downstream": trace_downstream,
    "find_alternate_sources": find_alternate_sources,
    "lineage": lineage,
    "run_cypher": run_cypher,
}


def tool_specs(backend: GraphBackend) -> list[dict]:
    """The tools this backend can actually serve.

    Offering run_cypher against the memory backend would spend agent steps on a
    call that can only fail, so it is withheld unless Cypher is supported.
    """
    if backend.supports_cypher:
        return list(TOOL_SPECS)
    return [s for s in TOOL_SPECS if s["function"]["name"] != "run_cypher"]


def execute(
    name: str, args: dict, backend: GraphBackend, shacl_report=None
) -> ToolResult:
    """Dispatch one tool call. Never raises: failures come back as ToolResults."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return ToolResult(
            data=None, summary=f"unknown tool '{name}'",
            error=(f"No tool named '{name}'. Available: {', '.join(TOOL_NAMES)}."),
        )

    kwargs = {k: v for k, v in (args or {}).items() if k != "reason"}
    if name == "supplier_delay_impact":
        kwargs["shacl_report"] = shacl_report

    try:
        return handler(backend, **kwargs)
    except ToolError as exc:
        return ToolResult(data=None, summary=str(exc), error=str(exc))
    except TypeError as exc:
        # Wrong or missing arguments -- tell the model precisely, so it can retry.
        return ToolResult(data=None, summary=f"bad arguments for {name}",
                          error=f"Bad arguments for {name}: {exc}")
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return ToolResult(data=None, summary=f"{name} failed",
                          error=f"{name} failed: {exc}")
