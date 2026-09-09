"""Cross-check LLM prose against the computed figures.

The system's central promise is that no dollar figure originates in a language
model. This module enforces it: every monetary quantity the narrator wrote is
extracted and matched against the set the financial engine actually produced.
An unmatched figure is a fault, reported and never silently accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.models import AvoidancePlan, FinancialExposure, TraversalResult

# $1,234,567.89 | $95.6M | $4.2K | 1,234,567 USD
_MONEY = re.compile(
    r"(?:USD\s*)?\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KMB])?(?:\s*(?:USD|dollars))?",
    re.IGNORECASE,
)
_SCALE = {"k": 1e3, "m": 1e6, "b": 1e9}


@dataclass
class Discrepancy:
    stated: float
    nearest_computed: float | None
    relative_error: float | None
    context: str


@dataclass
class CrossCheckResult:
    agreement: float = 1.0
    checked: int = 0
    matched: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.discrepancies


def _extract(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for m in _MONEY.finditer(text):
        raw, suffix = m.group(1), (m.group(2) or "").lower()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suffix:
            value *= _SCALE[suffix]
        elif value < 1000 and "," not in raw:
            # Bare small integers are day counts, order counts, percentages --
            # not money. Only treat them as money when explicitly marked.
            if "$" not in m.group(0) and "usd" not in m.group(0).lower():
                continue
        start, end = max(0, m.start() - 45), min(len(text), m.end() + 45)
        out.append((value, text[start:end].replace("\n", " ").strip()))
    return out


def computed_figures(
    exposure: FinancialExposure,
    traversal: TraversalResult,
    plan: AvoidancePlan | None,
) -> set[float]:
    """Every monetary value the deterministic engines actually produced."""
    figures: set[float] = {
        exposure.po_stranded_value, exposure.production_halt_cost,
        exposure.revenue_at_risk, exposure.penalty_exposure,
        exposure.total_financial_exposure,
    }
    figures.update(c.total_exposure for c in exposure.by_customer)
    figures.update(c.revenue_at_risk for c in exposure.by_customer)
    figures.update(c.penalty_exposure for c in exposure.by_customer)
    figures.update(po.net_value for po in traversal.purchase_orders)
    figures.update(so.net_value for so in traversal.sales_orders)
    figures.update(d.order_value for d in traversal.deliveries)
    figures.update(d.penalty_amount for d in traversal.deliveries)
    figures.update(m.unit_cost for m in traversal.materials)
    if plan:
        figures.update({plan.exposure_before, plan.exposure_after,
                        plan.total_avoidance_cost, plan.total_risk_mitigated})
        for a in plan.actions:
            figures.update({a.cost, a.risk_mitigated})
    return {f for f in figures if f}


def verify_narrative(
    narrative: str | None,
    exposure: FinancialExposure,
    traversal: TraversalResult,
    plan: AvoidancePlan | None = None,
    settings=None,
) -> CrossCheckResult:
    settings = settings or get_settings()
    tolerance = settings.llm_divergence_tolerance

    if not narrative:
        return CrossCheckResult(
            agreement=1.0,
            notes=["No LLM narrative to verify; deterministic figures stand alone."],
        )

    truth = computed_figures(exposure, traversal, plan)
    if not truth:
        return CrossCheckResult(agreement=1.0, notes=["No computed figures to compare."])

    result = CrossCheckResult(agreement=1.0)
    for stated, context in _extract(narrative):
        result.checked += 1
        nearest = min(truth, key=lambda t: abs(t - stated))
        # A figure written as "$95.6M" is a legitimate rounding of 95,552,000.
        rel = abs(nearest - stated) / max(abs(nearest), 1.0)
        if rel <= max(tolerance, 0.01):
            result.matched += 1
        else:
            result.discrepancies.append(Discrepancy(
                stated=stated, nearest_computed=nearest,
                relative_error=round(rel, 4), context=context,
            ))

    if result.checked:
        result.agreement = result.matched / result.checked

    if result.discrepancies:
        result.notes.append(
            f"{len(result.discrepancies)} figure(s) in the narrative do not match any "
            f"computed value within {tolerance:.0%}. The computed values are "
            f"authoritative and are what the report returns."
        )
    elif result.checked:
        result.notes.append(
            f"All {result.checked} monetary figures in the narrative trace to a "
            f"computed value."
        )
    return result
