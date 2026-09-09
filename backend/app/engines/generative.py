"""Generative layer -- optional prose and natural-language parsing.

Two jobs, both degradable:

  translate_query  NL question -> impact parameters. Falls back to a
                   deterministic parser, so /api/query works with no LLM.
  narrate          Executive summary over an already-computed report. Returns
                   None with no LLM; the report is complete without it.

The narrator is given the figures and told to phrase them. It is never asked to
compute anything -- and validation/cross_check.py verifies it obeyed.
"""

from __future__ import annotations

import difflib
import logging
import re

from app.engines.llm import get_llm
from app.models import AvoidancePlan, FinancialExposure, TraversalResult

logger = logging.getLogger(__name__)

QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_id": {"type": "string"},
        "supplier_name": {"type": "string"},
        "delay_days": {"type": "integer"},
        "horizon_days": {"type": "integer"},
    },
    "required": ["supplier_id", "delay_days"],
}

_DAY_PATTERNS = (
    r"(\d+)\s*[- ]?\s*day",
    r"delayed\s+by\s+(\d+)",
    r"slip(?:s|ped|ping)?\s+(\d+)",
    r"\+\s*(\d+)\s*d\b",
)


def parse_query_deterministic(
    question: str, suppliers: list[dict], backend=None
) -> dict:
    """Rule-based NL parse. No LLM, no network, always available."""
    q = question.lower()

    delay = 14
    for pat in _DAY_PATTERNS:
        m = re.search(pat, q)
        if m:
            delay = int(m.group(1))
            break

    horizon = 45
    m = re.search(r"(?:next|within|over)\s+(\d+)\s*days?", q)
    if m:
        horizon = max(int(m.group(1)), delay + 1)

    supplier_id, score = None, 0.0
    for s in suppliers:
        lifnr, name = s["LIFNR"], s.get("NAME1", "")
        if lifnr in question or lifnr.lstrip("0") in question:
            supplier_id, score = lifnr, 1.0
            break
        name_l = name.lower()
        if name_l and name_l in q:
            supplier_id, score = lifnr, 1.0
            break
        # Fuzzy: match on any distinctive word of the supplier name.
        for token in (t for t in re.split(r"\W+", name_l) if len(t) > 3):
            if token in q:
                supplier_id, score = lifnr, max(score, 0.85)
                break
        if score < 0.8 and name_l:
            r = difflib.SequenceMatcher(None, name_l, q).ratio()
            if r > score and r > 0.45:
                supplier_id, score = lifnr, r

    # People ask about the part, not the vendor: "what if we lose our sole
    # source for MCU-32?". Resolve the material to its primary supplier.
    via_material = None
    if supplier_id is None and backend is not None:
        via_material = _supplier_via_material(q, backend)
        if via_material:
            supplier_id, score = via_material["lifnr"], 0.9

    out = {
        "supplier_id": supplier_id,
        "delay_days": delay,
        "horizon_days": horizon,
        "match_confidence": round(score, 2),
        "parsed_by": "deterministic",
    }
    if via_material:
        out["resolved_via_material"] = via_material
    return out


def _supplier_via_material(q: str, backend) -> dict | None:
    """Find a material named in the question, then its primary source (EINA/EINE)."""
    tables = getattr(backend, "t", None)
    materials = tables["materials"] if tables else []
    best = None
    for m in materials:
        matnr = m["MATNR"]
        # Match the material number, or a distinctive word of its description.
        if matnr.lower() in q:
            best = (matnr, len(matnr))
            break
        for token in (t for t in re.split(r"\W+", m.get("MAKTX", "").lower())
                      if len(t) > 5):
            if token in q and (best is None or len(token) > best[1]):
                best = (matnr, len(token))
    if not best:
        return None

    matnr = best[0]
    sources = [r for r in (tables["source_list"] if tables else [])
               if r["MATNR"] == matnr]
    if not sources:
        return None
    primary = next((r for r in sources if r.get("is_primary")), sources[0])
    sup = backend.supplier(primary["LIFNR"]) or {}
    return {
        "matnr": matnr,
        "lifnr": primary["LIFNR"],
        "supplier_name": sup.get("NAME1", primary["LIFNR"]),
        "is_sole_source": len(sources) == 1,
        "note": (f"Question named material {matnr}; resolved to its primary source "
                 f"{sup.get('NAME1', primary['LIFNR'])} via EINA/EINE."),
    }


def translate_query(question: str, suppliers: list[dict], backend=None) -> dict:
    """LLM parse when available, verified against the deterministic parse."""
    fallback = parse_query_deterministic(question, suppliers, backend)
    llm = get_llm()
    if not llm.available:
        return fallback

    roster = "\n".join(f"- {s['LIFNR']}: {s.get('NAME1','')}" for s in suppliers)
    out = llm.complete_json(
        system=(
            "You map a supply-chain question to impact-analysis parameters. "
            "supplier_id MUST be one of the listed LIFNR values, copied exactly. "
            "delay_days is the delay in days (default 14). "
            "horizon_days is the look-ahead window (default 45)."
        ),
        user=f"Suppliers:\n{roster}\n\nQuestion: {question}",
        schema=QUERY_SCHEMA,
    )
    if not out:
        return fallback

    valid = {s["LIFNR"] for s in suppliers}
    sid = str(out.get("supplier_id", "")).strip()
    if sid not in valid:
        # The model invented a supplier: keep the grounded parse.
        logger.warning("LLM returned unknown supplier_id %r; using deterministic parse", sid)
        return fallback
    try:
        delay = int(out.get("delay_days", fallback["delay_days"]))
        horizon = int(out.get("horizon_days", fallback["horizon_days"]))
    except (TypeError, ValueError):
        return fallback

    return {
        "supplier_id": sid,
        "delay_days": max(1, delay),
        "horizon_days": max(delay + 1, horizon),
        "match_confidence": 1.0 if sid == fallback["supplier_id"] else 0.7,
        "parsed_by": "llm",
        "deterministic_agreed": sid == fallback["supplier_id"],
    }


def narrate(
    traversal: TraversalResult,
    exposure: FinancialExposure,
    plan: AvoidancePlan | None,
) -> str | None:
    """Executive summary. None when no LLM is configured or reachable."""
    llm = get_llm()
    if not llm.available:
        return None

    top = sorted(traversal.deliveries, key=lambda d: -d.order_value)[:4]
    facts = [
        f"Supplier: {traversal.supplier_name} ({traversal.supplier_id})",
        f"Delay: {traversal.delay_days} days",
        f"Total financial exposure: {exposure.total_financial_exposure:,.0f} USD",
        f"  PO stranded value: {exposure.po_stranded_value:,.0f}",
        f"  Production halt cost: {exposure.production_halt_cost:,.0f}",
        f"  Revenue at risk: {exposure.revenue_at_risk:,.0f}",
        f"  Penalty exposure: {exposure.penalty_exposure:,.0f}",
        f"Affected: {len(traversal.purchase_orders)} PO lines, "
        f"{len([m for m in traversal.materials if m.shortfall_qty > 0])} short materials, "
        f"{len(traversal.plants)} plants, {len(traversal.production_orders)} production "
        f"orders, {len(traversal.deliveries)} deliveries, {len(traversal.customers)} customers",
    ]
    for m in traversal.materials:
        if m.shortfall_qty > 0:
            facts.append(
                f"Shortfall: {m.matnr} at plant {m.werks} short {m.shortfall_qty:,.0f} units "
                f"(need {m.required_qty:,.0f}, have {m.on_hand_qty:,.0f})"
            )
    for d in top:
        facts.append(
            f"Delivery {d.vbeln} to {d.customer_name}: {d.days_late:.0f} days late, "
            f"order value {d.order_value:,.0f}, penalty {d.penalty_amount:,.0f}"
        )
    if plan and plan.actions:
        facts.append(
            f"Mitigation: {len(plan.actions)} actions costing "
            f"{plan.total_avoidance_cost:,.0f} remove {plan.total_risk_mitigated:,.0f} "
            f"({plan.mitigation_pct:.1%}), leaving {plan.exposure_after:,.0f}"
        )
        for a in plan.actions:
            facts.append(f"  Action: {a.title} - cost {a.cost:,.0f}, "
                         f"mitigates {a.risk_mitigated:,.0f}")

    return llm.complete(
        system=(
            "You are a supply chain analyst briefing an executive. Write 3 to 5 short "
            "paragraphs of plain prose.\n"
            "HARD RULES:\n"
            "1. Use ONLY the figures given. Never compute, estimate, round differently, "
            "or introduce a number that is not in the facts.\n"
            "2. Quote monetary figures exactly as provided, and write USD "
            "immediately after every monetary figure (e.g. '95,552,000 USD'). "
            "Never attach USD to a quantity, a day count, a percentage, a plant "
            "code or an order number.\n"
            "3. No bullet points, no headings, no markdown.\n"
            "4. Lead with the total exposure and who is affected, then the mechanism, "
            "then the recommended actions."
        ),
        user="Facts:\n" + "\n".join(facts),
    )
