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

# A monetary figure must be *marked* as one. Prose is full of numbers that are
# not money -- plant codes ("Plant 1010"), quantities ("2,850 units"), order
# numbers ("000009002"), day counts, percentages. Treating those as currency
# produced false hallucination reports, which is worse than not checking at all:
# it flags a faithful narrative and trains the reader to ignore the warning.
#
# So: only figures carrying an explicit currency marker are checked. The
# narrator is instructed to mark every one (see engines/generative.py), which
# makes an unmarked monetary claim itself a detectable failure.
_NUM = r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KMB])?"

_MONEY_PATTERNS = (
    re.compile(r"\$\s*" + _NUM, re.IGNORECASE),                    # $95.6M, $1,234
    re.compile(_NUM + r"\s*(?:USD|dollars)\b", re.IGNORECASE),     # 95,552,000 USD
    re.compile(r"USD\s*" + _NUM, re.IGNORECASE),                    # USD 95,552,000
)

# Units that prove a number is not currency, even if it sits near money words.
_NON_MONEY_SUFFIX = re.compile(
    r"^\s*(?:units?|pcs|ea|days?|hours?|weeks?|percent|%|deliveries|delivery|"
    r"customers?|plants?|materials?|orders?|lines?|hops?|items?)\b",
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
    """Every explicitly-marked monetary figure in the text, with its context."""
    found: dict[int, tuple[float, str]] = {}

    for pattern in _MONEY_PATTERNS:
        for m in pattern.finditer(text):
            raw, suffix = m.group(1), (m.group(2) or "").lower()

            # Skip a number glued to an identifier, e.g. the "9002" inside
            # "000009002" or the "7" in "PWR-IC-7".
            lead = text[m.start(1) - 1] if m.start(1) > 0 else " "
            if lead.isalnum() or lead in "-_/":
                continue
            if _NON_MONEY_SUFFIX.match(text[m.end():]):
                continue

            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue
            if suffix:
                value *= _SCALE[suffix]
            if value == 0:
                continue

            lo, hi = max(0, m.start() - 45), min(len(text), m.end() + 45)
            found[m.start(1)] = (value, text[lo:hi].replace("\n", " ").strip())

    return list(found.values())


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
