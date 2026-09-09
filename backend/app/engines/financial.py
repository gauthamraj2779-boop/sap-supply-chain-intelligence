"""Financial quantification.

The single origin of every dollar figure in the system. Business leaders read
the number, so the number has to survive being probed: each component states
its SAP source, and every non-SAP input is declared as an explicit assumption
rather than hidden in a constant.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.config import get_settings
from app.graph.adapter import GraphBackend
from app.models import (
    CustomerExposure,
    FinancialExposure,
    TimelineEvent,
    TraversalResult,
)


def compute_exposure(
    traversal: TraversalResult, backend: GraphBackend, settings=None
) -> FinancialExposure:
    settings = settings or get_settings()
    assumptions: list[str] = []

    # ---- 1. PO stranded value ------------------------------------------
    # Only PO lines whose material actually ends up short are "stranded":
    # capital committed to goods that will arrive too late to be used as
    # planned. A delayed line into a well-stocked material strands nothing.
    short_keys = {
        (m.matnr, m.werks) for m in traversal.materials if m.shortfall_qty > 0
    }
    po_stranded = sum(
        po.net_value for po in traversal.purchase_orders
        if (po.matnr, po.werks) in short_keys
    )
    if traversal.purchase_orders:
        excluded = len(traversal.purchase_orders) - sum(
            1 for po in traversal.purchase_orders if (po.matnr, po.werks) in short_keys
        )
        if excluded:
            assumptions.append(
                f"{excluded} delayed PO line(s) excluded from stranded value: "
                f"stock covers the requirement, so nothing is stranded (EKPO.NETWR, MARD.LABST)."
            )

    # ---- 2. Production halt cost ---------------------------------------
    # Halted orders at the same plant overlap in time, so summing halt days per
    # order would bill the same idle day several times. Charging the longest
    # halt per plant is the conservative reading.
    halt_by_plant: dict[str, float] = {}
    for po in traversal.production_orders:
        halt_by_plant[po.werks] = max(halt_by_plant.get(po.werks, 0.0), po.halt_days)

    halt_cost = 0.0
    for werks, days in halt_by_plant.items():
        plant = backend.plant(werks) or {}
        rate = float(
            plant.get("idle_plant_cost_per_day")
            or settings.default_idle_plant_cost_per_day
        )
        halt_cost += rate * days
        assumptions.append(
            f"Plant {werks} ({plant.get('NAME1', werks)}): {days:.0f} disrupted days "
            f"x {rate:,.0f}/day idle cost. Idle cost is a management accounting "
            f"input, not an SAP field."
        )
    if len(halt_by_plant) > 1 or any(
        len([p for p in traversal.production_orders if p.werks == w]) > 1
        for w in halt_by_plant
    ):
        assumptions.append(
            "Production halt cost charges the LONGEST halt per plant, not the sum "
            "across orders: concurrent halts share the same idle days."
        )

    # ---- 3. Revenue at risk --------------------------------------------
    revenue = sum(so.net_value for so in traversal.sales_orders)
    if revenue:
        assumptions.append(
            "Revenue at risk is the full net value of affected sales order items "
            "(VBAP.NETWR) -- a worst case treating delayed revenue as unrecognised, "
            "not a forecast of lost revenue."
        )

    # ---- 4. Penalty exposure -------------------------------------------
    penalty = sum(d.penalty_amount for d in traversal.deliveries)
    if penalty:
        rates = sorted({d.penalty_rate for d in traversal.deliveries if d.days_late > 0})
        assumptions.append(
            "Late-delivery penalty rates ("
            + ", ".join(f"{r:.0%}" for r in rates)
            + ") are contract terms held outside SAP core tables."
        )

    total = po_stranded + halt_cost + revenue + penalty

    # ---- by-customer roll-up -------------------------------------------
    by_cust: dict[str, CustomerExposure] = {}
    for so in traversal.sales_orders:
        ce = by_cust.setdefault(so.kunnr, CustomerExposure(
            kunnr=so.kunnr, customer_name=so.customer_name,
            revenue_at_risk=0.0, penalty_exposure=0.0,
            total_exposure=0.0, deliveries_at_risk=0,
        ))
        ce.revenue_at_risk += so.net_value
    for dv in traversal.deliveries:
        ce = by_cust.setdefault(dv.kunnr, CustomerExposure(
            kunnr=dv.kunnr, customer_name=dv.customer_name,
            revenue_at_risk=0.0, penalty_exposure=0.0,
            total_exposure=0.0, deliveries_at_risk=0,
        ))
        ce.penalty_exposure += dv.penalty_amount
        if dv.days_late > 0:
            ce.deliveries_at_risk += 1
    for ce in by_cust.values():
        ce.total_exposure = ce.revenue_at_risk + ce.penalty_exposure

    return FinancialExposure(
        po_stranded_value=round(po_stranded, 2),
        production_halt_cost=round(halt_cost, 2),
        revenue_at_risk=round(revenue, 2),
        penalty_exposure=round(penalty, 2),
        total_financial_exposure=round(total, 2),
        by_customer=sorted(by_cust.values(), key=lambda c: -c.total_exposure),
        assumptions=assumptions,
    )


def build_timeline(
    traversal: TraversalResult, exposure: FinancialExposure
) -> list[TimelineEvent]:
    """When each domino falls, with exposure accumulating as it does."""
    as_of = traversal.as_of_date
    events: list[tuple[date, str, str, float, str]] = []

    events.append((
        as_of, "Supplier delay announced",
        f"{traversal.supplier_name} notifies a {traversal.delay_days}-day slip",
        0.0, "trigger",
    ))

    for po in sorted(traversal.purchase_orders, key=lambda p: p.original_delivery_date)[:3]:
        events.append((
            po.original_delivery_date, f"PO {po.ebeln}-{po.ebelp} breached",
            f"{po.material_name} ({po.menge:,.0f} units) misses committed "
            f"EKET.EINDT; arrives {po.delayed_delivery_date.isoformat()}",
            exposure.po_stranded_value, "purchase_order",
        ))

    for m in sorted(
        (m for m in traversal.materials if m.stockout_date and m.shortfall_qty > 0),
        key=lambda m: m.stockout_date,
    )[:3]:
        events.append((
            m.stockout_date, f"{m.matnr} depleted at plant {m.werks}",
            f"Stock exhausted; shortfall {m.shortfall_qty:,.0f} units against "
            f"{m.required_qty:,.0f} required",
            exposure.po_stranded_value, "material",
        ))

    running = exposure.po_stranded_value + exposure.production_halt_cost
    for po in sorted(traversal.production_orders, key=lambda p: p.scheduled_finish)[:3]:
        events.append((
            po.scheduled_finish, f"Production order {po.aufnr} halted",
            f"{po.output_material_name} at {po.plant_name} slips "
            f"{po.halt_days:.0f} days (blocked by {', '.join(po.blocking_materials)})",
            running, "production",
        ))

    running_total = running
    for dv in sorted(traversal.deliveries, key=lambda d: d.planned_goods_issue):
        running_total += dv.order_value + dv.penalty_amount
        events.append((
            dv.planned_goods_issue, f"Delivery {dv.vbeln} misses date",
            f"{dv.customer_name}: {dv.days_late:.0f} days late, "
            f"penalty {dv.penalty_amount:,.0f}",
            min(running_total, exposure.total_financial_exposure), "delivery",
        ))

    events.sort(key=lambda e: e[0])
    return [
        TimelineEvent(
            day_offset=(d - as_of).days, event_date=d, label=label,
            detail=detail, cumulative_exposure=round(cum, 2), kind=kind,
        )
        for d, label, detail, cum, kind in events
    ]


def headline(traversal: TraversalResult, exposure: FinancialExposure) -> str:
    if exposure.total_financial_exposure <= 0:
        return (
            f"No material financial exposure from a {traversal.delay_days}-day delay "
            f"at {traversal.supplier_name}: existing stock covers all requirements "
            f"in the horizon."
        )
    return (
        f"{_money(exposure.total_financial_exposure)} exposure from a "
        f"{traversal.delay_days}-day delay at {traversal.supplier_name} - affecting "
        f"{len(traversal.purchase_orders)} POs, "
        f"{len([m for m in traversal.materials if m.shortfall_qty > 0])} materials, "
        f"{len(traversal.plants)} plants, "
        f"{len(traversal.production_orders)} production orders and "
        f"{len(traversal.deliveries)} customer deliveries."
    )


def _money(v: float) -> str:
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"
