"""Generative layer -- optional prose and natural-language parsing.

Four jobs, all degradable:

  translate_query     NL question -> impact parameters. Falls back to a
                      deterministic parser, so /api/query works with no LLM.
  translate_to_cypher NL question -> a read-only graph query, built against the
                      real schema and validated in code before it can run.
  narrate             Executive summary over an already-computed report.
                      Returns None with no LLM; the report is complete without it.
  write_action_plan   Business prose for each computed avoidance action, added
                      alongside the deterministic text and never replacing it.

The model is given the figures and told to phrase them. It is never asked to
compute anything -- and validation/cross_check.py verifies it obeyed.
"""

from __future__ import annotations

import difflib
import logging
import re

from app.engines.llm import get_llm
from app.graph.adapter import GraphUnavailable
from app.graph.schema import EDGE_TYPES, NODE_TYPES
from app.models import (
    AvoidanceAction,
    AvoidancePlan,
    CypherTranslation,
    FinancialExposure,
    TraversalResult,
)
from app.validation.cross_check import verify_narrative

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
    # The deterministic parser resolves supplier, delay and horizon for every
    # question shape this system answers, in microseconds. Consulting a model
    # first added ~30s to a request whose result it almost never changed, so
    # the model is now only asked when the rules fail to identify a supplier.
    """LLM parse when available, verified against the deterministic parse."""
    fallback = parse_query_deterministic(question, suppliers, backend)
    llm = get_llm()
    if not llm.available:
        return fallback
    if fallback.get("supplier_id") and fallback.get("match_confidence", 0) >= 0.85:
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


# --------------------------------------------------------------------------
# Question -> Cypher
# --------------------------------------------------------------------------
# A generated query is untrusted input that is about to run against the graph,
# so nothing about it is taken on the model's word. The prompt is built from
# schema.py rather than from prose, and every rule the prompt states is
# re-checked here in code before the query goes anywhere near a session.

CYPHER_ROW_LIMIT = 100

CYPHER_SCHEMA = {
    "type": "object",
    "properties": {
        "cypher": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["cypher"],
}

_WRITE_CLAUSE = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|FOREACH)\b", re.IGNORECASE
)
_LOAD_CSV = re.compile(r"\bLOAD\s+CSV\b", re.IGNORECASE)
_PROCEDURE = re.compile(r"\bCALL\s+(db|dbms|apoc|gds)\s*\.", re.IGNORECASE)
_LIMIT = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
_MATCH = re.compile(r"\bMATCH\b", re.IGNORECASE)


def cypher_schema_prompt() -> str:
    """The graph's real vocabulary, rendered for the prompt.

    Generated from NODE_TYPES/EDGE_TYPES so the model is shown the labels,
    properties and relationship directions that actually exist. A label the
    model was not shown is a label the validator will reject.
    """
    lines = ["Node labels, their key and their properties:"]
    for nt in NODE_TYPES.values():
        props = list(dict.fromkeys(f.graph_property for f in nt.fields))
        lines.append(
            f"  (:{nt.label}) key={nt.key_property}"
            f" properties: {', '.join(props) or nt.key_property}"
            f"  -- {nt.business_definition}"
        )
    lines.append("")
    lines.append("Relationships, in the only direction they exist:")
    for e in EDGE_TYPES:
        lines.append(
            f"  (:{e.source_label})-[:{e.type}]->(:{e.target_label})"
            f"  -- {e.business_meaning}"
        )
    return "\n".join(lines)


def _strip_noise(query: str) -> str:
    """Blank out comments and string literals before scanning for keywords.

    A material described as 'Fastener Set M8' must not read as a SET clause,
    and a label named inside a comment must not count as one used.
    """
    q = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)
    q = re.sub(r"//[^\n]*", " ", q)
    q = re.sub(r"'(?:\\.|[^'\\])*'", "''", q)
    q = re.sub(r'"(?:\\.|[^"\\])*"', '""', q)
    # Property maps use the same colon syntax as labels, so drop them: in
    # {lifnr: '0000001000'} the key is not a label.
    for _ in range(3):
        q = re.sub(r"\{[^{}]*\}", " ", q)
    return q


def _vocabulary_used(stripped: str) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    for inner in re.findall(r"\(([^()]*)\)", stripped):
        labels += re.findall(r"[:|]\s*([A-Za-z_][A-Za-z0-9_]*)", inner)
    rel_types: list[str] = []
    for inner in re.findall(r"\[([^\[\]]*)\]", stripped):
        rel_types += re.findall(r"[:|]\s*([A-Za-z_][A-Za-z0-9_]*)", inner)
    return list(dict.fromkeys(labels)), list(dict.fromkeys(rel_types))


class CypherValidation:
    """Verdict on one candidate query, plus the query as it would be run."""

    def __init__(self, ok: bool, query: str, reason: str | None = None,
                 limit_injected: bool = False,
                 labels: list[str] | None = None,
                 rel_types: list[str] | None = None) -> None:
        self.ok = ok
        self.query = query
        self.reason = reason
        self.limit_injected = limit_injected
        self.labels = labels or []
        self.rel_types = rel_types or []


def validate_cypher(query: str, row_limit: int = CYPHER_ROW_LIMIT) -> CypherValidation:
    """Read-only + schema gate. Rejects rather than sanitises anything unsafe."""
    candidate = (query or "").strip().rstrip(";").strip()
    if not candidate:
        return CypherValidation(False, candidate, "The model produced no query.")

    stripped = _strip_noise(candidate)

    if ";" in stripped:
        return CypherValidation(
            False, candidate, "Rejected: multiple statements in one query."
        )

    m = _WRITE_CLAUSE.search(stripped)
    if m:
        return CypherValidation(
            False, candidate,
            f"Rejected: '{m.group(1).upper()}' is a write clause and this path is "
            f"read-only.",
        )
    if _LOAD_CSV.search(stripped):
        return CypherValidation(False, candidate, "Rejected: LOAD CSV is not permitted.")
    m = _PROCEDURE.search(stripped)
    if m:
        return CypherValidation(
            False, candidate,
            f"Rejected: procedure calls into '{m.group(1).lower()}.' are not permitted.",
        )
    if not _MATCH.search(stripped):
        return CypherValidation(
            False, candidate,
            "Rejected: the query does not MATCH anything, so it reads nothing from "
            "the graph.",
        )

    labels, rel_types = _vocabulary_used(stripped)
    unknown_labels = [x for x in labels if x not in NODE_TYPES]
    if unknown_labels:
        return CypherValidation(
            False, candidate,
            f"Rejected: label(s) {', '.join(sorted(unknown_labels))} are not in the "
            f"schema. Known labels: {', '.join(sorted(NODE_TYPES))}.",
            labels=labels, rel_types=rel_types,
        )
    known_rels = {e.type for e in EDGE_TYPES}
    unknown_rels = [x for x in rel_types if x not in known_rels]
    if unknown_rels:
        return CypherValidation(
            False, candidate,
            f"Rejected: relationship type(s) {', '.join(sorted(unknown_rels))} are not "
            f"in the schema. Known types: {', '.join(sorted(known_rels))}.",
            labels=labels, rel_types=rel_types,
        )

    # An unbounded query against a real graph is a denial of service. The bound
    # is added rather than the query refused, since the intent is legitimate.
    limit_injected = False
    if not _LIMIT.search(stripped):
        candidate = f"{candidate}\nLIMIT {row_limit}"
        limit_injected = True

    return CypherValidation(
        True, candidate, None, limit_injected=limit_injected,
        labels=labels, rel_types=rel_types,
    )


def translate_to_cypher(question: str, schema: str | None = None) -> CypherTranslation:
    """Turn a question into a validated, read-only Cypher query.

    ``schema`` overrides the schema description put in front of the model; by
    default the real NODE_TYPES/EDGE_TYPES vocabulary is used.
    """
    llm = get_llm()
    if not llm.available:
        reason = llm.status().reason
        return CypherTranslation(
            question=question,
            valid=False,
            reason=(f"No LLM is configured, so no query could be generated ({reason}). "
                    f"The deterministic endpoints are unaffected."),
            generated_by=f"unavailable ({reason})",
        )

    out = llm.complete_json(
        system=(
            "You translate a supply-chain question into ONE read-only Neo4j Cypher "
            "query over the schema below.\n\n"
            f"{schema or cypher_schema_prompt()}\n\n"
            "HARD RULES:\n"
            "1. Use ONLY the labels, relationship types and properties listed above. "
            "Never invent a label, a relationship type or a property.\n"
            "2. Read only. Never write CREATE, MERGE, DELETE, SET, REMOVE, DROP, "
            "FOREACH, LOAD CSV, or any CALL into db., dbms., apoc. or gds.\n"
            "3. Exactly one statement, no trailing semicolon, no code fences.\n"
            f"4. Always end with an explicit LIMIT of at most {CYPHER_ROW_LIMIT}.\n"
            "5. RETURN named values, not whole nodes, so the result is a table.\n"
            "6. Follow relationships only in the direction shown above."
        ),
        user=f"Question: {question}",
        schema=CYPHER_SCHEMA,
    )
    if not out:
        return CypherTranslation(
            question=question, valid=False,
            reason="The model did not return a usable query.",
            generated_by=f"{llm.status().provider}:{llm.status().model}",
        )

    raw = str(out.get("cypher", "")).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("cypher").strip()

    verdict = validate_cypher(raw)
    if not verdict.ok:
        logger.warning("Generated Cypher rejected: %s", verdict.reason)
    return CypherTranslation(
        question=question,
        query=verdict.query,
        valid=verdict.ok,
        reason=verdict.reason,
        generated_by=f"{llm.status().provider}:{llm.status().model}",
        limit_injected=verdict.limit_injected,
        labels_used=verdict.labels,
        relationship_types_used=verdict.rel_types,
    )


def _jsonable(row: dict) -> dict:
    """Coerce driver-native values (dates, nodes) into serialisable ones."""
    plain = (str, int, float, bool, type(None), list, dict)
    return {k: (v if isinstance(v, plain) else str(v)) for k, v in row.items()}


def execute_cypher(backend, translation: CypherTranslation) -> CypherTranslation:
    """Run a validated query, or say precisely why it could not be run."""
    if not translation.valid or not translation.query:
        return translation
    try:
        rows = backend.run_cypher(translation.query)
    except GraphUnavailable as exc:
        translation.execution_note = (
            f"{exc} The query above was generated and validated but not executed; "
            f"no results are invented in its place."
        )
        return translation
    except Exception as exc:
        logger.warning("Generated Cypher failed at execution: %s", exc)
        translation.execution_note = f"The database rejected the query: {exc}"
        return translation

    translation.executed = True
    translation.rows = [_jsonable(r) for r in rows]
    translation.row_count = len(translation.rows)
    translation.execution_note = f"Executed against the '{backend.name}' backend."
    return translation


# --------------------------------------------------------------------------
# Action plan writer
# --------------------------------------------------------------------------
# The avoidance engine computes what to do; this turns it into something an
# executive reads. The computed action is still what the report returns -- the
# prose rides alongside it in ``narrative`` and is dropped the moment it
# disagrees with a figure, so the deterministic text always survives.

ACTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "narratives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "narrative": {"type": "string"},
                },
                "required": ["index", "narrative"],
            },
        }
    },
    "required": ["narratives"],
}

# Quantities and durations carry no currency marker, so cross_check cannot see
# them. They are checked here against the numbers the model was actually given.
_MEASURED = re.compile(
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*-?\s*(units?|pcs|ea|days?|weeks?)\b", re.IGNORECASE
)


def _numbers_in(*texts: str) -> set[float]:
    found: set[float] = set()
    for t in texts:
        for m in re.finditer(r"[0-9][0-9,]*(?:\.[0-9]+)?", t or ""):
            try:
                found.add(float(m.group().replace(",", "")))
            except ValueError:
                continue
    return found


def _unsupported_measure(
    text: str, action: AvoidanceAction, traversal: TraversalResult
) -> float | None:
    """First quantity or duration in the prose that the model was never given."""
    allowed = _numbers_in(action.title, action.description, *action.evidence)
    allowed |= {action.qty_covered, float(traversal.delay_days)}
    if action.lead_time_days is not None:
        allowed.add(action.lead_time_days)

    for m in _MEASURED.finditer(text):
        try:
            stated = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if not any(abs(stated - a) <= max(1.0, abs(a) * 0.01) for a in allowed):
            return stated
    return None


def _action_facts(plan: AvoidancePlan, traversal: TraversalResult) -> str:
    blocks = [
        f"Scenario: supplier {traversal.supplier_name} ({traversal.supplier_id}) "
        f"delayed {traversal.delay_days} days.",
        f"Plan totals: cost {plan.total_avoidance_cost:,.0f} USD, exposure removed "
        f"{plan.total_risk_mitigated:,.0f} USD, exposure remaining "
        f"{plan.exposure_after:,.0f} USD.",
        "",
    ]
    for i, a in enumerate(plan.actions):
        blocks.append(f"[{i}] kind={a.kind}")
        blocks.append(f"    computed title: {a.title}")
        blocks.append(
            f"    material: {a.target_matnr} ({a.target_material_name}) "
            f"at plant {a.target_werks}"
        )
        blocks.append(f"    quantity covered: {a.qty_covered:,.0f} units")
        if a.lead_time_days is not None:
            blocks.append(f"    lead time: {a.lead_time_days:,.0f} days")
        blocks.append(f"    cost: {a.cost:,.0f} USD")
        blocks.append(f"    exposure removed: {a.risk_mitigated:,.0f} USD")
        blocks.append(f"    return on spend: {a.roi_display}")
        blocks.append(f"    proven against: {a.sap_source}")
        for e in a.evidence:
            blocks.append(f"    evidence: {e}")
        blocks.append("")
    return "\n".join(blocks)


def write_action_plan(
    plan: AvoidancePlan,
    traversal: TraversalResult,
    exposure: FinancialExposure | None = None,
) -> AvoidancePlan:
    """Attach business prose to each computed action, in place.

    Every generated narrative goes through the same figure cross-check the
    executive summary does. One that states a figure the engines did not compute
    is discarded outright, the action keeps its deterministic text, and what
    happened is recorded on ``plan.narrative_notes``.
    """
    if not plan.actions:
        return plan

    llm = get_llm()
    if not llm.available:
        plan.narrative_source = f"unavailable ({llm.status().reason})"
        return plan

    source = f"{llm.status().provider}:{llm.status().model}"
    out = llm.complete_json(
        system=(
            "You are a supply chain analyst writing the recommendation section of an "
            "executive brief. For each numbered action below write 2 to 3 sentences of "
            "plain prose saying what to do, why it is feasible, and what it buys.\n"
            "HARD RULES:\n"
            "1. Use ONLY the figures given for that action. Never compute, re-scale, "
            "round differently, or introduce a number that is not in its facts.\n"
            "2. Write USD immediately after every monetary figure (e.g. '12,500 USD'). "
            "Never attach USD to a quantity, a day count, a percentage, a plant code "
            "or an order number.\n"
            "3. No bullet points, no headings, no markdown, no action titles.\n"
            "4. Return one entry per action, copying its index exactly."
        ),
        user=_action_facts(plan, traversal),
        schema=ACTION_PLAN_SCHEMA,
        max_tokens=1400,
    )
    if not out or not isinstance(out.get("narratives"), list):
        plan.narrative_source = f"{source} (no usable response)"
        plan.narrative_notes.append(
            "The model returned no usable action prose; every action shows its "
            "computed text."
        )
        return plan

    accepted, rejected = 0, 0
    for item in out["narratives"]:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", -1))
        except (TypeError, ValueError):
            continue
        text = str(item.get("narrative", "")).strip()
        if not text or not 0 <= idx < len(plan.actions):
            continue

        action = plan.actions[idx]
        if exposure is not None:
            cross = verify_narrative(text, exposure, traversal, plan)
            if not cross.clean:
                d = cross.discrepancies[0]
                rejected += 1
                plan.narrative_notes.append(
                    f"Action {idx} ({action.kind}): generated prose discarded -- it "
                    f"stated {d.stated:,.0f} against a nearest computed value of "
                    f"{d.nearest_computed:,.0f}. The computed text stands."
                )
                continue

        stray = _unsupported_measure(text, action, traversal)
        if stray is not None:
            rejected += 1
            plan.narrative_notes.append(
                f"Action {idx} ({action.kind}): generated prose discarded -- it stated "
                f"a quantity or duration of {stray:,.0f} that no computed value "
                f"supports. The computed text stands."
            )
            continue

        action.narrative = text
        accepted += 1

    plan.narrative_source = source
    plan.narrative_notes.append(
        f"{accepted} of {accepted + rejected} generated action narratives passed the "
        f"figure cross-check. Cost, exposure removed, ROI, quantity and lead time are "
        f"the avoidance engine's, unaltered, in every case."
    )
    return plan
