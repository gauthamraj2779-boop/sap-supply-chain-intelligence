"""Pipeline orchestration.

Runs the full analysis in dependency order and assembles the report:

    traversal -> financial -> avoidance -> [narrative] -> cross-check -> confidence

The bracketed step is the only optional one, and its failure never propagates.
"""

from __future__ import annotations

import logging
from datetime import date

from app.engines import avoidance, deterministic, financial, generative
from app.engines.llm import get_llm
from app.graph.adapter import GraphBackend
from app.models import (
    AffectedCounts,
    GraphEdge,
    GraphNode,
    ImpactReport,
    LineageStep,
    LineageTrail,
    SupplierInfo,
    TraversalResult,
)
from app.validation import compute_confidence, validate, verify_narrative
from app.validation.shacl_validator import ValidationReport

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def analyse(
    backend: GraphBackend,
    supplier_id: str,
    delay_days: int,
    horizon_days: int = deterministic.DEFAULT_HORIZON_DAYS,
    as_of: date | None = None,
    include_narrative: bool = True,
    shacl_report: ValidationReport | None = None,
) -> ImpactReport:
    warnings: list[str] = []

    # 1 - deterministic traversal (authoritative)
    traversal = deterministic.run_traversal(
        backend, supplier_id, delay_days, horizon_days=horizon_days, as_of=as_of
    )
    if traversal.hops_failed:
        warnings.append(
            f"Traversal incomplete: {', '.join(traversal.hops_failed)}. "
            f"Figures below cover the hops that did complete."
        )

    # 2 - financial quantification (the only source of dollar figures)
    exposure = financial.compute_exposure(traversal, backend)
    if not exposure.self_consistent():
        warnings.append(
            "Financial components do not sum to the reported total; "
            "treat the breakdown as authoritative."
        )

    # 3 - avoidance
    try:
        plan = avoidance.find_actions(backend, traversal, exposure)
    except Exception as exc:
        logger.exception("Avoidance engine failed")
        plan = None
        warnings.append(f"Avoidance engine unavailable: {exc}")

    # 4 - narrative (optional; never blocks)
    llm = get_llm()
    narrative, source = None, "unavailable"
    if include_narrative and llm.available:
        narrative = generative.narrate(traversal, exposure, plan)
        source = f"{llm.status().provider}:{llm.status().model}" if narrative else "failed"
        if not narrative:
            warnings.append(
                "LLM narrative could not be generated; all figures below are unaffected."
            )
    elif include_narrative:
        source = f"unavailable ({llm.status().reason})"

    # 5 - cross-check: the LLM may phrase figures, never invent them
    cross = verify_narrative(narrative, exposure, traversal, plan)
    if cross.discrepancies:
        warnings.append(
            f"{len(cross.discrepancies)} figure(s) in the narrative did not match a "
            f"computed value and are contradicted by the structured results below."
        )

    # 6 - confidence
    shacl = shacl_report if shacl_report is not None else validate(backend)
    confidence = compute_confidence(
        traversal, shacl, cross,
        graph_backend_name=backend.name, llm_available=llm.available,
    )

    supplier = _supplier_info(backend, traversal)
    counts = _affected_counts(traversal)
    time_to_impact = _time_to_impact(traversal)
    critical_path = _critical_path(traversal, exposure)

    nodes, edges = build_blast_radius(traversal, exposure, backend)

    return ImpactReport(
        supplier_id=traversal.supplier_id,
        supplier_name=traversal.supplier_name,
        supplier=supplier,
        delay_days=traversal.delay_days,
        as_of_date=traversal.as_of_date,
        affected_counts=counts,
        time_to_impact_days=time_to_impact,
        critical_path=critical_path,
        headline=financial.headline(traversal, exposure),
        financial_exposure=exposure,
        traversal=traversal,
        timeline=financial.build_timeline(traversal, exposure),
        avoidance=plan,
        confidence=confidence,
        narrative=narrative,
        narrative_source=source,
        blast_radius_nodes=nodes,
        blast_radius_edges=edges,
        warnings=warnings,
    )


def _supplier_info(backend: GraphBackend, traversal: TraversalResult) -> SupplierInfo:
    """Supplier card, including which materials it is the ONLY source for.

    Sole-sourcing is the structural reason a delay cascades at all, so it is
    computed from EINA/EINE rather than asserted in the UI copy.
    """
    raw = backend.supplier(traversal.supplier_id) or {}
    sole: list[str] = []
    for m in traversal.materials:
        alternates = backend.alternate_sources(m.matnr, traversal.supplier_id)
        if not alternates:
            sole.append(m.matnr)
    return SupplierInfo(
        lifnr=traversal.supplier_id,
        name=traversal.supplier_name,
        country=raw.get("LAND1"),
        risk_score=raw.get("risk_score"),
        sole_source_materials=sorted(set(sole)),
    )


def _affected_counts(traversal: TraversalResult) -> AffectedCounts:
    return AffectedCounts(
        purchase_orders=len(traversal.purchase_orders),
        materials=len(traversal.materials),
        materials_short=len([m for m in traversal.materials if m.shortfall_qty > 0]),
        plants=len(traversal.plants),
        production_orders=len(traversal.production_orders),
        sales_orders=len(traversal.sales_orders),
        deliveries=len(traversal.deliveries),
        customers=len(traversal.customers),
    )


def _time_to_impact(traversal: TraversalResult) -> int | None:
    """Days until the first material actually runs out."""
    dates = [m.stockout_date for m in traversal.materials
             if m.stockout_date and m.shortfall_qty > 0]
    if not dates:
        return None
    return max(0, (min(dates) - traversal.as_of_date).days)


def _critical_path(traversal: TraversalResult, exposure) -> LineageTrail | None:
    """Stitch the single largest exposure back to the supplier, hop by hop.

    This is the trail a sceptical reviewer follows: biggest delivery at risk ->
    its sales order -> the production order that feeds it -> the material that
    blocks it -> the PO line that was late.
    """
    if not traversal.deliveries:
        return None
    dv = max(traversal.deliveries, key=lambda d: d.order_value + d.penalty_amount)
    so = next((s for s in traversal.sales_orders if s.vbeln == dv.ref_sales_order), None)
    apo = next((p for p in traversal.production_orders
                if so and p.output_matnr == so.matnr), None)
    mat = None
    if apo and apo.blocking_materials:
        mat = next((m for m in traversal.materials
                    if m.matnr == apo.blocking_materials[0] and m.werks == apo.werks), None)
    po = next((p for p in traversal.purchase_orders
               if mat and p.matnr == mat.matnr and p.werks == mat.werks), None)

    steps: list[LineageStep] = [
        LineageStep(sap_table="LFA1", sap_field="LIFNR",
                    key=f"LIFNR={traversal.supplier_id}", value=traversal.supplier_name,
                    meaning="Delayed supplier"),
    ]
    for row in (po, mat, apo, so, dv):
        if row is not None:
            steps.extend(row.lineage.steps)

    parts = [s for s in (
        po.lineage.derivation if po else None,
        mat.lineage.derivation if mat else None,
        apo.lineage.derivation if apo else None,
        dv.lineage.derivation,
    ) if s]

    return LineageTrail(
        subject=(f"Largest single exposure: delivery {dv.vbeln} to {dv.customer_name} "
                 f"({dv.order_value + dv.penalty_amount:,.0f})"),
        steps=steps,
        derivation=" -> ".join(parts),
    )


def build_blast_radius(
    traversal: TraversalResult, exposure, backend: GraphBackend | None = None
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Nodes and edges for the frontend, sized by exposure and coloured by severity."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def node(nid, label, caption, severity="none", exposure_val=0.0,
             sap_table="", sap_fields=None, lineage=None, **props):
        existing = nodes.get(nid)
        if existing:
            if _SEVERITY_RANK[severity] > _SEVERITY_RANK[existing.severity]:
                existing.severity = severity
            existing.exposure = max(existing.exposure, exposure_val)
            if sap_fields:
                existing.sap_fields.update(sap_fields)
            if lineage and not existing.lineage:
                existing.lineage = lineage
            return existing
        n = GraphNode(id=nid, label=label, caption=caption, severity=severity,
                      exposure=round(exposure_val, 2), properties=props,
                      sap_table=sap_table, sap_fields=sap_fields or {},
                      lineage=lineage)
        nodes[nid] = n
        return n

    sid = f"Supplier:{traversal.supplier_id}"
    sup_raw = backend.supplier(traversal.supplier_id) if backend else {}
    node(sid, "Supplier", traversal.supplier_name, "critical",
         exposure.total_financial_exposure,
         sap_table="LFA1",
         sap_fields={"LIFNR": traversal.supplier_id,
                     "NAME1": traversal.supplier_name,
                     "LAND1": (sup_raw or {}).get("LAND1", "")},
         lifnr=traversal.supplier_id, delay_days=traversal.delay_days)

    short = {(m.matnr, m.werks): m for m in traversal.materials}

    for po in traversal.purchase_orders:
        pid = f"PurchaseOrder:{po.ebeln}/{po.ebelp}"
        m = short.get((po.matnr, po.werks))
        sev = m.severity if m else "none"
        node(pid, "PurchaseOrder", f"PO {po.ebeln}-{po.ebelp}", sev, po.net_value,
             sap_table="EKKO/EKPO/EKET",
             sap_fields={"EBELN": po.ebeln, "EBELP": po.ebelp, "MATNR": po.matnr,
                         "MENGE": po.menge, "NETWR": po.net_value,
                         "EINDT": po.original_delivery_date.isoformat()},
             lineage=po.lineage,
             ebeln=po.ebeln, net_value=po.net_value,
             original_date=po.original_delivery_date.isoformat(),
             delayed_date=po.delayed_delivery_date.isoformat())
        edges.append(GraphEdge(source=sid, target=pid, type="FULFILLS",
                               derived_from="EKKO.LIFNR -> LFA1.LIFNR"))

    for m in traversal.materials:
        mid = f"Material:{m.matnr}@{m.werks}"
        node(mid, "Material", f"{m.matnr} @ {m.werks}", m.severity,
             m.shortfall_qty * m.unit_cost,
             sap_table="MARA/MARC/MARD",
             sap_fields={"MATNR": m.matnr, "MAKTX": m.material_name,
                         "WERKS": m.werks, "LABST": m.on_hand_qty,
                         "BDMNG (sum)": m.required_qty},
             lineage=m.lineage,
             matnr=m.matnr, werks=m.werks,
             shortfall=m.shortfall_qty, on_hand=m.on_hand_qty,
             required=m.required_qty, days_of_coverage=m.days_of_coverage)
        pid_plant = f"Plant:{m.werks}"
        node(pid_plant, "Plant", m.plant_name, m.severity, 0.0,
             sap_table="T001W",
             sap_fields={"WERKS": m.werks, "NAME1": m.plant_name},
             werks=m.werks)
        edges.append(GraphEdge(source=mid, target=pid_plant, type="STOCKED_AT",
                               derived_from="MARD.WERKS -> T001W.WERKS"))
        for po in traversal.purchase_orders:
            if po.matnr == m.matnr and po.werks == m.werks:
                edges.append(GraphEdge(
                    source=f"PurchaseOrder:{po.ebeln}/{po.ebelp}", target=mid,
                    type="ORDERS", derived_from="EKPO.MATNR -> MARA.MATNR"))

    for apo in traversal.production_orders:
        oid = f"ProductionOrder:{apo.aufnr}"
        node(oid, "ProductionOrder", f"Prod {apo.aufnr}", apo.severity, 0.0,
             sap_table="AFKO/AFPO/RESB",
             sap_fields={"AUFNR": apo.aufnr, "PLNBEZ": apo.output_matnr,
                         "GAMNG": apo.order_qty,
                         "GLTRP": apo.scheduled_finish.isoformat(),
                         "WERKS": apo.werks},
             lineage=apo.lineage,
             aufnr=apo.aufnr, output=apo.output_matnr, halt_days=apo.halt_days,
             scheduled_finish=apo.scheduled_finish.isoformat(),
             projected_finish=apo.projected_finish.isoformat())
        for matnr in apo.blocking_materials:
            edges.append(GraphEdge(source=f"Material:{matnr}@{apo.werks}", target=oid,
                                   type="BLOCKS", derived_from="RESB.MATNR -> MARA.MATNR"))
        edges.append(GraphEdge(source=oid, target=f"Plant:{apo.werks}", type="RUNS_AT",
                               derived_from="AFKO.WERKS -> T001W.WERKS"))

    out_to_order = {a.output_matnr: a.aufnr for a in traversal.production_orders}
    for so in traversal.sales_orders:
        soid = f"SalesOrder:{so.vbeln}/{so.posnr}"
        node(soid, "SalesOrder", f"SO {so.vbeln}", so.severity, so.net_value,
             sap_table="VBAK/VBAP",
             sap_fields={"VBELN": so.vbeln, "POSNR": so.posnr, "MATNR": so.matnr,
                         "KWMENG": so.order_qty, "NETWR": so.net_value,
                         "KUNNR": so.kunnr},
             lineage=so.lineage,
             vbeln=so.vbeln, net_value=so.net_value, matnr=so.matnr)
        aufnr = out_to_order.get(so.matnr)
        if aufnr:
            edges.append(GraphEdge(source=f"ProductionOrder:{aufnr}", target=soid,
                                   type="SUPPLIES_ORDER",
                                   derived_from="AFPO.MATNR -> VBAP.MATNR"))
        cid = f"Customer:{so.kunnr}"
        node(cid, "Customer", so.customer_name, so.severity, 0.0,
             sap_table="KNA1",
             sap_fields={"KUNNR": so.kunnr, "NAME1": so.customer_name},
             kunnr=so.kunnr)
        edges.append(GraphEdge(source=soid, target=cid, type="SOLD_TO",
                               derived_from="VBAK.KUNNR -> KNA1.KUNNR"))

    for dv in traversal.deliveries:
        did = f"Delivery:{dv.vbeln}"
        node(did, "Delivery", f"Dlv {dv.vbeln}", dv.severity,
             dv.order_value + dv.penalty_amount,
             sap_table="LIKP/LIPS",
             sap_fields={"VBELN": dv.vbeln, "KUNNR": dv.kunnr,
                         "LFDAT": dv.planned_goods_issue.isoformat(),
                         "VGBEL": dv.ref_sales_order,
                         "penalty_rate": dv.penalty_rate},
             lineage=dv.lineage,
             vbeln=dv.vbeln,
             days_late=dv.days_late, penalty=dv.penalty_amount,
             planned=dv.planned_goods_issue.isoformat(),
             projected=dv.projected_goods_issue.isoformat())
        edges.append(GraphEdge(source=did, target=f"Customer:{dv.kunnr}", type="SHIPS_TO",
                               derived_from="LIKP.KUNNR -> KNA1.KUNNR"))
        for so in traversal.sales_orders:
            if so.vbeln == dv.ref_sales_order:
                edges.append(GraphEdge(source=did,
                                       target=f"SalesOrder:{so.vbeln}/{so.posnr}",
                                       type="FULFILLS_ORDER",
                                       derived_from="LIPS.VGBEL -> VBAK.VBELN"))

    # Drop edges whose endpoints were not materialised.
    valid = set(nodes)
    edges = [e for e in edges if e.source in valid and e.target in valid]
    seen, unique = set(), []
    for e in edges:
        k = (e.source, e.target, e.type)
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return list(nodes.values()), unique
