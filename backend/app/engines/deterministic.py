"""Deterministic blast-radius traversal.

This module is the authority. No LLM participates here. Everything it returns
is derived arithmetically from graph records, and every returned row carries the
SAP table/field/key that produced it.

The traversal follows the eight hops:

    Supplier -> PurchaseOrder -> ScheduleLine -> Material@Plant
             -> ProductionOrder -> SalesOrder -> Delivery -> Customer
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.graph.adapter import GraphBackend
from app.models import (
    AffectedDelivery,
    AffectedMaterial,
    AffectedProductionOrder,
    AffectedPurchaseOrder,
    AffectedSalesOrder,
    LineageStep,
    LineageTrail,
    TraversalResult,
)

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 45

# Real bills of material are a handful of levels deep. This is not a modelling
# limit, it is the stopping condition for a BOM that references itself.
MAX_BOM_LEVELS = 12


class SupplierNotFound(LookupError):
    pass


def _d(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _severity_from_ratio(ratio: float) -> str:
    if ratio <= 0:
        return "none"
    if ratio < 0.10:
        return "low"
    if ratio < 0.30:
        return "medium"
    if ratio < 0.60:
        return "high"
    return "critical"


def _severity_from_days(days: float) -> str:
    if days <= 0:
        return "none"
    if days <= 3:
        return "low"
    if days <= 7:
        return "medium"
    if days <= 14:
        return "high"
    return "critical"


def _explode_bom(backend: GraphBackend, result: TraversalResult) -> None:
    """Carry a halted sub-assembly's slip up to the assemblies that consume it.

    Walks the BOM one level at a time from every halted order, so a raw-material
    shortfall travels raw -> sub-assembly -> finished good instead of stopping
    at the order that happens to reserve the raw part.

    The parent inherits the *root* blocking materials rather than the
    sub-assembly's material number. Those are the parts a buyer can actually do
    something about, and they are the keys the financial attribution and the
    avoidance plan are built on; attaching exposure to a sub-assembly nobody can
    purchase would strand it. The sub-assembly itself is recorded separately, in
    ``blocking_subassemblies``, so the path stays visible.
    """
    # One pass lifts the halt by one BOM level, and a pass only reports a change
    # when it adds an order or lengthens a halt -- both of which move in one
    # direction only, so an acyclic bill of material settles. The cap is the
    # safety net for a BOM that references itself: the walk stops and says so
    # rather than climbing for ever.
    for _ in range(MAX_BOM_LEVELS):
        if not _propagate_one_level(backend, result):
            return
    logger.warning(
        "BOM explosion stopped after %d levels; MAST/STPO may contain a cycle",
        MAX_BOM_LEVELS,
    )


def _propagate_one_level(backend: GraphBackend, result: TraversalResult) -> bool:
    changed = False
    for child in list(result.production_orders):
        if child.halt_days <= 0:
            continue
        assemblies = {r["MATNR"] for r in backend.where_used(child.output_matnr)}
        if not assemblies:
            continue

        # Sub-assembly stock already on the shelf is consumed in requirement-date
        # order; only what it fails to cover has to wait for the halted order.
        st = backend.stock(child.output_matnr, child.werks) or {}
        running = float(st.get("LABST", 0.0))
        for r in backend.reservations_for(child.output_matnr, child.werks):
            allocated = min(running, r["BDMNG"])
            running -= allocated
            if r["BDMNG"] - allocated <= 0:
                continue
            parent = backend.production_order(r["AUFNR"])
            if not parent or parent["output_MATNR"] not in assemblies:
                continue  # a reservation the bill of material does not corroborate

            bdter = _d(r["BDTER"])
            # Same arithmetic as hop 5, with the revised *finish* of the feeding
            # order standing in for the revised arrival of purchased goods.
            halt = max(0, (child.projected_finish - bdter).days)
            if halt <= 0:
                continue

            existing = next((x for x in result.production_orders
                             if x.aufnr == parent["AUFNR"]), None)
            if existing:
                if existing is child:
                    continue  # an order cannot be a component of itself
                if child.output_matnr not in existing.blocking_subassemblies:
                    existing.blocking_subassemblies.append(child.output_matnr)
                    changed = True
                for matnr in child.blocking_materials:
                    if matnr not in existing.blocking_materials:
                        existing.blocking_materials.append(matnr)
                        changed = True
                if halt > existing.halt_days:
                    existing.halt_days = float(halt)
                    existing.projected_finish = (
                        existing.scheduled_finish + timedelta(days=halt)
                    )
                    existing.severity = _severity_from_days(halt)
                    changed = True
                continue

            comp = next((c for c in backend.bom_for_material(parent["output_MATNR"])
                         if c["IDNRK"] == child.output_matnr), {})
            out_mat = backend.material(parent["output_MATNR"]) or {}
            plant = backend.plant(parent["WERKS"]) or {}
            sched_finish = _d(parent["GLTRP"])
            new = AffectedProductionOrder(
                aufnr=parent["AUFNR"], output_matnr=parent["output_MATNR"],
                output_material_name=out_mat.get("MAKTX", parent["output_MATNR"]),
                werks=parent["WERKS"], plant_name=plant.get("NAME1", parent["WERKS"]),
                order_qty=parent["GAMNG"], scheduled_finish=sched_finish,
                projected_finish=sched_finish + timedelta(days=halt),
                halt_days=float(halt),
                blocking_materials=list(child.blocking_materials),
                blocking_subassemblies=[child.output_matnr],
                severity=_severity_from_days(halt),
                lineage=LineageTrail(
                    subject=f"Production order {parent['AUFNR']}",
                    steps=[
                        LineageStep(
                            sap_table="STPO", sap_field="IDNRK",
                            key=f"STLNR={comp.get('STLNR', '')}/POSNR={comp.get('POSNR', '')}",
                            value=child.output_matnr,
                            meaning="Sub-assembly the bill of material puts into this order's output"),
                        LineageStep(
                            sap_table="STPO", sap_field="MENGE",
                            key=f"STLNR={comp.get('STLNR', '')}/POSNR={comp.get('POSNR', '')}",
                            value=f"{comp.get('MENGE', 0):,.0f} per {comp.get('BMENG', 1):,.0f}",
                            meaning="Component quantity per BOM base quantity (STKO.BMENG)"),
                        LineageStep(
                            sap_table="RESB", sap_field="BDTER",
                            key=f"RSNUM={r['RSNUM']}/RSPOS={r['RSPOS']}",
                            value=bdter.isoformat(),
                            meaning="Date this order needs the sub-assembly"),
                        LineageStep(
                            sap_table="AFKO", sap_field="GLTRP",
                            key=f"AUFNR={child.aufnr}",
                            value=child.projected_finish.isoformat(),
                            meaning="Revised finish of the order that builds the sub-assembly"),
                    ],
                    derivation=(
                        f"{parent['output_MATNR']} consumes {child.output_matnr} "
                        f"(STPO.IDNRK); {r['BDMNG'] - allocated:,.0f} of the "
                        f"{r['BDMNG']:,.0f} required are uncovered by stock, so the "
                        f"order waits on {child.aufnr}: halt_days = revised finish "
                        f"{child.projected_finish.isoformat()} - need date "
                        f"{bdter.isoformat()} = {halt}d"
                    ),
                ),
            )
            result.production_orders.append(new)
            changed = True
    return changed


def run_traversal(
    backend: GraphBackend,
    supplier_id: str,
    delay_days: int,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    as_of: date | None = None,
) -> TraversalResult:
    as_of = as_of or date.today()
    horizon_end = as_of + timedelta(days=horizon_days)

    supplier = backend.supplier(supplier_id)
    if not supplier:
        raise SupplierNotFound(f"No supplier with LIFNR={supplier_id}")

    result = TraversalResult(
        supplier_id=supplier_id,
        supplier_name=supplier.get("NAME1", supplier_id),
        delay_days=delay_days,
        as_of_date=as_of,
    )
    result.hops_completed.append("supplier")

    # ---------------------------------------------------------------- HOP 1-2
    # Purchase orders and their dated schedule lines (EKKO -> EKPO -> EKET)
    try:
        lines = [
            sl for sl in backend.open_schedule_lines_for_supplier(supplier_id)
            if _d(sl["EINDT"]) <= horizon_end
        ]
        for sl in lines:
            orig = _d(sl["EINDT"])
            result.purchase_orders.append(AffectedPurchaseOrder(
                ebeln=sl["EBELN"], ebelp=sl["EBELP"], matnr=sl["MATNR"],
                material_name=sl.get("TXZ01", ""), werks=sl["WERKS"],
                menge=sl["MENGE"], net_value=sl["NETWR"],
                original_delivery_date=orig,
                delayed_delivery_date=orig + timedelta(days=delay_days),
                delay_days=delay_days,
                lineage=LineageTrail(
                    subject=f"PO {sl['EBELN']}-{sl['EBELP']}",
                    steps=[
                        LineageStep(sap_table="EKKO", sap_field="LIFNR",
                                    key=f"EBELN={sl['EBELN']}", value=supplier_id,
                                    meaning="Supplier on the purchase order"),
                        LineageStep(sap_table="EKPO", sap_field="NETWR",
                                    key=f"EBELN={sl['EBELN']}/EBELP={sl['EBELP']}",
                                    value=f"{sl['NETWR']:,.2f}",
                                    meaning="Net order value of the PO line"),
                        LineageStep(sap_table="EKET", sap_field="EINDT",
                                    key=f"EBELN={sl['EBELN']}/EBELP={sl['EBELP']}/ETENR={sl.get('ETENR','0001')}",
                                    value=orig.isoformat(),
                                    meaning="Committed delivery date, now slipping"),
                    ],
                    derivation=f"delayed_delivery_date = EKET.EINDT + {delay_days}d "
                               f"= {(orig + timedelta(days=delay_days)).isoformat()}",
                ),
            ))
        result.hops_completed += ["purchase_orders", "schedule_lines"]
    except Exception as exc:
        logger.exception("Hop purchase_orders failed")
        result.hops_failed += ["purchase_orders", "schedule_lines"]
        return result

    if not result.purchase_orders:
        # Nothing inbound in the horizon: a real, correct "no impact" answer.
        result.hops_completed += ["materials", "plants", "production_orders",
                                  "sales_orders", "deliveries", "customers"]
        return result

    # ---------------------------------------------------------------- HOP 3-4
    # Material availability per plant. This is where the shortfall is computed.
    affected_keys = {(po.matnr, po.werks) for po in result.purchase_orders}
    # Earliest delayed arrival per material/plant drives the coverage window.
    arrival: dict[tuple[str, str], date] = {}
    for po in result.purchase_orders:
        k = (po.matnr, po.werks)
        arrival[k] = min(arrival.get(k, po.delayed_delivery_date),
                         po.delayed_delivery_date)

    try:
        for matnr, werks in sorted(affected_keys):
            mat = backend.material(matnr) or {}
            plant = backend.plant(werks) or {}
            st = backend.stock(matnr, werks) or {"LABST": 0.0, "EISBE": 0.0}
            on_hand = float(st["LABST"])
            unit_cost = float(mat.get("unit_cost", 0.0))
            new_date = arrival[(matnr, werks)]

            other_inbound = sum(
                r["MENGE"] for r in backend.inbound_schedule_lines(
                    matnr, werks, exclude_lifnr=supplier_id
                ) if _d(r["EINDT"]) <= new_date
            )

            reservations = backend.reservations_for(matnr, werks)
            in_window = [r for r in reservations if _d(r["BDTER"]) <= new_date]
            required = sum(r["BDMNG"] for r in in_window)
            horizon_demand = sum(
                r["BDMNG"] for r in reservations if _d(r["BDTER"]) <= horizon_end
            )

            available = on_hand + other_inbound
            shortfall = max(0.0, required - available)

            daily = horizon_demand / horizon_days if horizon_days else 0.0
            coverage = (on_hand / daily) if daily > 0 else float("inf")
            gap = max(0.0, delay_days - coverage) if daily > 0 else 0.0

            # Chronological allocation gives the exact date stock runs out.
            stockout, running = None, available
            for r in sorted(in_window, key=lambda x: x["BDTER"]):
                running -= r["BDMNG"]
                if running < 0:
                    stockout = _d(r["BDTER"])
                    break

            ratio = (shortfall / required) if required > 0 else 0.0
            result.materials.append(AffectedMaterial(
                matnr=matnr, material_name=mat.get("MAKTX", matnr),
                werks=werks, plant_name=plant.get("NAME1", werks),
                on_hand_qty=on_hand, other_inbound_qty=float(other_inbound),
                required_qty=float(required), shortfall_qty=shortfall,
                unit_cost=unit_cost, daily_consumption=round(daily, 4),
                days_of_coverage=round(coverage, 2) if daily > 0 else 9999.0,
                gap_days=round(gap, 2), stockout_date=stockout,
                severity=_severity_from_ratio(ratio),
                lineage=LineageTrail(
                    subject=f"{matnr} @ {werks}",
                    steps=[
                        LineageStep(sap_table="MARD", sap_field="LABST",
                                    key=f"MATNR={matnr}/WERKS={werks}",
                                    value=f"{on_hand:,.0f}",
                                    meaning="Unrestricted-use stock on hand"),
                        LineageStep(sap_table="RESB", sap_field="BDMNG",
                                    key=f"MATNR={matnr}/WERKS={werks} ({len(in_window)} reservations)",
                                    value=f"{required:,.0f}",
                                    meaning="Component quantity required before the delayed arrival"),
                        LineageStep(sap_table="EKET", sap_field="EINDT",
                                    key=f"MATNR={matnr}/WERKS={werks}",
                                    value=new_date.isoformat(),
                                    meaning="Revised arrival date after the delay"),
                    ],
                    derivation=(
                        f"shortfall = required - (on_hand + other_inbound) = "
                        f"{required:,.0f} - ({on_hand:,.0f} + {other_inbound:,.0f}) "
                        f"= {shortfall:,.0f} {mat.get('MEINS','EA')}"
                    ),
                ),
            ))
            if werks not in result.plants:
                result.plants.append(werks)
        result.hops_completed += ["materials", "plants"]
    except Exception:
        logger.exception("Hop materials failed")
        result.hops_failed += ["materials", "plants"]
        return result

    # ---------------------------------------------------------------- HOP 5
    # Production orders: allocate the stock that exists, in requirement-date
    # order. Whatever is left uncovered waits for the delayed goods.
    try:
        for m in result.materials:
            if m.shortfall_qty <= 0:
                continue
            new_date = arrival[(m.matnr, m.werks)]
            running = m.on_hand_qty + m.other_inbound_qty
            for r in backend.reservations_for(m.matnr, m.werks):
                bdter = _d(r["BDTER"])
                if bdter > new_date:
                    continue
                allocated = min(running, r["BDMNG"])
                running -= allocated
                uncovered = r["BDMNG"] - allocated
                if uncovered <= 0:
                    continue

                po = backend.production_order(r["AUFNR"])
                if not po:
                    continue
                halt = max(0, (new_date - bdter).days)
                sched_finish = _d(po["GLTRP"])
                existing = next((x for x in result.production_orders
                                 if x.aufnr == po["AUFNR"]), None)
                if existing:
                    if m.matnr not in existing.blocking_materials:
                        existing.blocking_materials.append(m.matnr)
                    if halt > existing.halt_days:
                        existing.halt_days = float(halt)
                        existing.projected_finish = sched_finish + timedelta(days=halt)
                        existing.severity = _severity_from_days(halt)
                    continue

                out_mat = backend.material(po["output_MATNR"]) or {}
                plant = backend.plant(po["WERKS"]) or {}
                result.production_orders.append(AffectedProductionOrder(
                    aufnr=po["AUFNR"], output_matnr=po["output_MATNR"],
                    output_material_name=out_mat.get("MAKTX", po["output_MATNR"]),
                    werks=po["WERKS"], plant_name=plant.get("NAME1", po["WERKS"]),
                    order_qty=po["GAMNG"], scheduled_finish=sched_finish,
                    projected_finish=sched_finish + timedelta(days=halt),
                    halt_days=float(halt), blocking_materials=[m.matnr],
                    severity=_severity_from_days(halt),
                    lineage=LineageTrail(
                        subject=f"Production order {po['AUFNR']}",
                        steps=[
                            LineageStep(sap_table="RESB", sap_field="BDMNG",
                                        key=f"RSNUM={r['RSNUM']}/RSPOS={r['RSPOS']}",
                                        value=f"{r['BDMNG']:,.0f}",
                                        meaning="Component quantity this order requires"),
                            LineageStep(sap_table="RESB", sap_field="BDTER",
                                        key=f"RSNUM={r['RSNUM']}/RSPOS={r['RSPOS']}",
                                        value=bdter.isoformat(),
                                        meaning="Date the component is needed"),
                            LineageStep(sap_table="AFKO", sap_field="GLTRP",
                                        key=f"AUFNR={po['AUFNR']}",
                                        value=sched_finish.isoformat(),
                                        meaning="Scheduled finish date of the order"),
                        ],
                        derivation=(
                            f"uncovered = {r['BDMNG']:,.0f} - {allocated:,.0f} allocated "
                            f"= {uncovered:,.0f}; halt_days = revised arrival "
                            f"{new_date.isoformat()} - need date {bdter.isoformat()} = {halt}d"
                        ),
                    ),
                ))

        # RESB stops at the order that reserves the short component, so on its
        # own the cascade ends at the sub-assembly. The BOM is what carries it
        # the rest of the way to the finished good.
        _explode_bom(backend, result)
        result.hops_completed.append("production_orders")
    except Exception:
        logger.exception("Hop production_orders failed")
        result.hops_failed.append("production_orders")
        return result

    # ---------------------------------------------------------------- HOP 6-8
    # Downstream demand: sales orders, deliveries, customers.
    try:
        seen_so: set[str] = set()
        halt_by_order: dict[str, float] = {}
        for apo in result.production_orders:
            for si in backend.sales_items_for_material(apo.output_matnr):
                key = f"{si['VBELN']}/{si['POSNR']}"
                if key in seen_so:
                    continue
                seen_so.add(key)
                halt_by_order[si["VBELN"]] = max(
                    halt_by_order.get(si["VBELN"], 0.0), apo.halt_days
                )
                result.sales_orders.append(AffectedSalesOrder(
                    vbeln=si["VBELN"], posnr=si["POSNR"], kunnr=si["KUNNR"],
                    customer_name=si["customer_name"], matnr=si["MATNR"],
                    order_qty=si["KWMENG"], net_value=si["NETWR"],
                    severity=apo.severity,
                    lineage=LineageTrail(
                        subject=f"Sales order {si['VBELN']}-{si['POSNR']}",
                        steps=[
                            LineageStep(sap_table="AFPO", sap_field="MATNR",
                                        key=f"AUFNR={apo.aufnr}", value=apo.output_matnr,
                                        meaning="Material produced by the halted order"),
                            LineageStep(sap_table="VBAP", sap_field="NETWR",
                                        key=f"VBELN={si['VBELN']}/POSNR={si['POSNR']}",
                                        value=f"{si['NETWR']:,.2f}",
                                        meaning="Net value of the sales order item"),
                            LineageStep(sap_table="VBAK", sap_field="KUNNR",
                                        key=f"VBELN={si['VBELN']}", value=si["KUNNR"],
                                        meaning="Customer that placed the order"),
                        ],
                        derivation=f"Production order {apo.aufnr} slips {apo.halt_days:.0f}d, "
                                   f"delaying the material this order demands",
                    ),
                ))
                if si["KUNNR"] and si["KUNNR"] not in result.customers:
                    result.customers.append(si["KUNNR"])
        result.hops_completed.append("sales_orders")

        for aso in result.sales_orders:
            slip = halt_by_order.get(aso.vbeln, 0.0)
            for dv in backend.deliveries_for_sales_order(aso.vbeln):
                if any(d.vbeln == dv["VBELN"] for d in result.deliveries):
                    continue
                lfdat = _d(dv["LFDAT"])
                projected = lfdat + timedelta(days=int(slip))
                days_late = max(0.0, float((projected - lfdat).days))
                order_value = dv.get("NETWR") or aso.net_value
                rate = float(dv.get("penalty_rate", 0.0))
                penalty = order_value * rate if days_late > 0 else 0.0
                result.deliveries.append(AffectedDelivery(
                    vbeln=dv["VBELN"], kunnr=dv["KUNNR"],
                    customer_name=dv["customer_name"], ref_sales_order=aso.vbeln,
                    planned_goods_issue=lfdat, projected_goods_issue=projected,
                    days_late=days_late, order_value=float(order_value),
                    penalty_rate=rate, penalty_amount=round(penalty, 2),
                    severity=_severity_from_days(days_late),
                    lineage=LineageTrail(
                        subject=f"Delivery {dv['VBELN']}",
                        steps=[
                            LineageStep(sap_table="LIPS", sap_field="VGBEL",
                                        key=f"VBELN={dv['VBELN']}", value=aso.vbeln,
                                        meaning="Sales order this delivery fulfils"),
                            LineageStep(sap_table="LIKP", sap_field="LFDAT",
                                        key=f"VBELN={dv['VBELN']}", value=lfdat.isoformat(),
                                        meaning="Planned goods issue date"),
                            LineageStep(sap_table="LIKP", sap_field="KUNNR",
                                        key=f"VBELN={dv['VBELN']}", value=dv["KUNNR"],
                                        meaning="Customer receiving the shipment"),
                        ],
                        derivation=(
                            f"projected_goods_issue = LIKP.LFDAT + {slip:.0f}d upstream slip "
                            f"= {projected.isoformat()}; penalty = "
                            f"{order_value:,.0f} x {rate:.0%} = {penalty:,.0f}"
                        ),
                    ),
                ))
                if dv["KUNNR"] and dv["KUNNR"] not in result.customers:
                    result.customers.append(dv["KUNNR"])
        result.hops_completed += ["deliveries", "customers"]
    except Exception:
        logger.exception("Hop downstream failed")
        result.hops_failed += ["sales_orders", "deliveries", "customers"]

    return result
