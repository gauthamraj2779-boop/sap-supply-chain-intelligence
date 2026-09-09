"""Missing-value estimation, flagged in the open.

Real SAP extracts have holes: a purchase order item that never got a NETWR, a
material with no costing view. Dropping such a line understates exposure;
filling it in quietly overstates certainty. This module does neither. It
derives the value from records that *are* present, publishes the basis and the
sample size, marks the value as estimated, and feeds the count back into
``data_completeness`` so the confidence score carries the cost of the guess.

No estimate is ever a constant. Every one is an average of, or an arithmetic
identity over, figures that exist in the extract:

  NETWR   mean net value per unit across sibling lines (same material first,
          then same material group), else the material's unit cost x quantity.
  unit    mean EINE.NETPR across the material's approved sources, else the
  cost    mean unit cost of its material group.

The shipped dataset is complete, so on the demo data this module finds nothing
and the report is unchanged. tests/test_estimation.py constructs the gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import EstimatedValue, TraversalResult


@dataclass
class EstimationResult:
    """Everything the estimator did, and how much of the path it covered."""

    estimates: list[EstimatedValue] = field(default_factory=list)
    line_items_examined: int = 0
    unresolved: list[str] = field(default_factory=list)

    @property
    def assumptions(self) -> list[str]:
        out: list[str] = []
        if self.estimates:
            out.append(
                f"{len(self.estimates)} of {self.line_items_examined} line item(s) on "
                f"this analysis path had no usable value in the source record. Each was "
                f"estimated from comparable records, flagged as estimated, and lowers "
                f"the data-completeness component of the confidence score. See "
                f"`estimates` for the basis and sample size behind every one. The "
                f"exposure figures above are computed only from values that are present "
                f"in the records, so they read as a floor rather than a point estimate."
            )
        if self.unresolved:
            out.append(
                f"{len(self.unresolved)} line item(s) could not even be estimated -- no "
                f"comparable priced record exists ({', '.join(self.unresolved[:3])}"
                f"{', ...' if len(self.unresolved) > 3 else ''}). They contribute zero to "
                f"the exposure, so the total is a floor rather than a point estimate."
            )
        return out


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _mean_per_unit(rows: list[dict], qty_field: str) -> tuple[float, int] | None:
    """Mean net value per unit over rows that carry both a value and a quantity."""
    rates = [
        _num(r.get("NETWR")) / _num(r.get(qty_field))
        for r in rows
        if _num(r.get("NETWR")) > 0 and _num(r.get(qty_field)) > 0
    ]
    if not rates:
        return None
    return sum(rates) / len(rates), len(rates)


def _estimate_net_value(
    row: dict, peers: list[dict], qty_field: str, mat_index: dict[str, dict]
) -> tuple[float, str, int] | None:
    """Estimate one line's net value. None when no comparable record exists."""
    qty = _num(row.get(qty_field))
    if qty <= 0:
        # Without a quantity there is no unit rate to scale, and inventing one
        # would be exactly the fabrication this module exists to avoid.
        return None

    matnr = str(row.get("MATNR", ""))
    mat = mat_index.get(matnr, {})
    matkl = mat.get("MATKL")

    same_material = [p for p in peers if str(p.get("MATNR", "")) == matnr]
    hit = _mean_per_unit(same_material, qty_field)
    if hit:
        rate, n = hit
        return qty * rate, (
            f"mean NETWR/unit of {rate:,.2f} across {n} MATNR={matnr} line(s), "
            f"x quantity {qty:,.0f}"
        ), n

    if matkl:
        group = [
            p for p in peers
            if mat_index.get(str(p.get("MATNR", "")), {}).get("MATKL") == matkl
        ]
        hit = _mean_per_unit(group, qty_field)
        if hit:
            rate, n = hit
            return qty * rate, (
                f"mean NETWR/unit of {rate:,.2f} across {n} MATKL={matkl} line(s), "
                f"x quantity {qty:,.0f}"
            ), n

    unit_cost = _num(mat.get("unit_cost"))
    if unit_cost > 0:
        return qty * unit_cost, (
            f"MARA unit cost {unit_cost:,.2f} for {matnr} x quantity {qty:,.0f}"
        ), 1

    hit = _mean_per_unit(peers, qty_field)
    if hit:
        rate, n = hit
        return qty * rate, (
            f"mean NETWR/unit of {rate:,.2f} across {n} priced line(s) of any material "
            f"group, x quantity {qty:,.0f}"
        ), n
    return None


def _estimate_unit_cost(
    mat: dict, materials: list[dict], sources: list[dict]
) -> tuple[float, str, int] | None:
    matnr = str(mat.get("MATNR", ""))

    prices = [
        _num(s.get("NETPR")) for s in sources
        if str(s.get("MATNR", "")) == matnr and _num(s.get("NETPR")) > 0
    ]
    if prices:
        mean = sum(prices) / len(prices)
        return mean, (
            f"mean EINE.NETPR of {mean:,.2f} across {len(prices)} approved source(s) "
            f"for {matnr}"
        ), len(prices)

    matkl = mat.get("MATKL")
    if matkl:
        peers = [
            _num(m.get("unit_cost")) for m in materials
            if m.get("MATKL") == matkl
            and str(m.get("MATNR", "")) != matnr
            and _num(m.get("unit_cost")) > 0
        ]
        if peers:
            mean = sum(peers) / len(peers)
            return mean, (
                f"mean MARA unit cost of {mean:,.2f} across {len(peers)} "
                f"MATKL={matkl} material(s)"
            ), len(peers)
    return None


def find_estimates(
    po_items: list[dict],
    so_items: list[dict],
    materials: list[dict],
    sources: list[dict] | None = None,
) -> EstimationResult:
    """Estimate every absent or non-positive value across the supplied records.

    Records are raw SAP-shaped dicts, so this is testable without a graph:
    EKPO lines carry MENGE/NETWR, VBAP lines KWMENG/NETWR, MARA rows
    MATKL/unit_cost, EINA/EINE rows NETPR.
    """
    sources = sources or []
    mat_index = {str(m.get("MATNR", "")): m for m in materials}
    result = EstimationResult()

    for rows, qty_field, entity, sap_field, key_fields in (
        (po_items, "MENGE", "PurchaseOrderItem", "EKPO.NETWR", ("EBELN", "EBELP")),
        (so_items, "KWMENG", "SalesOrderItem", "VBAP.NETWR", ("VBELN", "POSNR")),
    ):
        priced = [r for r in rows if _num(r.get("NETWR")) > 0]
        for row in rows:
            result.line_items_examined += 1
            if _num(row.get("NETWR")) > 0:
                continue
            key = "/".join(f"{f}={row.get(f, '?')}" for f in key_fields)
            hit = _estimate_net_value(row, priced, qty_field, mat_index)
            if hit is None:
                result.unresolved.append(f"{entity} {key}")
                continue
            value, basis, sample = hit
            result.estimates.append(EstimatedValue(
                entity=entity, key=key, sap_field=sap_field,
                estimated_value=round(value, 2), basis=basis, sample_size=sample,
            ))

    for mat in materials:
        result.line_items_examined += 1
        if _num(mat.get("unit_cost")) > 0:
            continue
        matnr = str(mat.get("MATNR", "?"))
        hit = _estimate_unit_cost(mat, materials, sources)
        if hit is None:
            result.unresolved.append(f"Material MATNR={matnr}")
            continue
        value, basis, sample = hit
        result.estimates.append(EstimatedValue(
            entity="Material", key=f"MATNR={matnr}", sap_field="MARA unit cost",
            estimated_value=round(value, 2), basis=basis, sample_size=sample,
        ))

    return result


def from_traversal(traversal: TraversalResult, backend) -> EstimationResult:
    """Run the estimator over the records this analysis actually read.

    Only the semantic backend surface is used, so this behaves identically on
    Neo4j and the in-process graph.
    """
    po_items = [
        {"EBELN": po.ebeln, "EBELP": po.ebelp, "MATNR": po.matnr,
         "MENGE": po.menge, "NETWR": po.net_value}
        for po in traversal.purchase_orders
    ]
    so_items = [
        {"VBELN": so.vbeln, "POSNR": so.posnr, "MATNR": so.matnr,
         "KWMENG": so.order_qty, "NETWR": so.net_value}
        for so in traversal.sales_orders
    ]

    matnrs = {po.matnr for po in traversal.purchase_orders}
    matnrs |= {so.matnr for so in traversal.sales_orders}
    matnrs |= {m.matnr for m in traversal.materials}

    materials: list[dict] = []
    sources: list[dict] = []
    for matnr in sorted(matnrs):
        raw = backend.material(matnr) or {}
        materials.append({
            "MATNR": matnr,
            "MATKL": raw.get("MATKL"),
            "unit_cost": raw.get("unit_cost", 0.0),
        })
        # Every approved source carries a negotiated price, so an uncosted
        # material is usually still priced in EINA/EINE. Only worth the lookup
        # when the costing view is the thing that is missing.
        if _num(raw.get("unit_cost")) <= 0:
            for alt in backend.alternate_sources(matnr, ""):
                sources.append({"MATNR": matnr, "NETPR": alt.get("NETPR")})

    return find_estimates(po_items, so_items, materials, sources)
