"""Explainable confidence.

Three published components, combined by a stated formula. The API returns the
components alongside the score, so "72% confident" can always be unpacked into
*why*. Nothing here is a learned or opaque weight.
"""

from __future__ import annotations

from app.models import ConfidenceScore, TraversalResult
from app.validation.cross_check import CrossCheckResult
from app.validation.shacl_validator import ValidationReport

FORMULA = (
    "overall = data_completeness^0.4 x traversal_coverage^0.4 x engine_agreement^0.2 "
    "(weighted geometric mean; any component near zero drags the score down, "
    "which is the intended behaviour)"
)
_W = {"data": 0.4, "coverage": 0.4, "agreement": 0.2}


def compute_confidence(
    traversal: TraversalResult,
    shacl: ValidationReport | None,
    cross: CrossCheckResult | None,
    graph_backend_name: str = "memory",
    llm_available: bool = False,
) -> ConfidenceScore:
    notes: list[str] = []
    degraded: list[str] = []

    # ---- data completeness --------------------------------------------
    if shacl is None or not shacl.available:
        data = 0.85
        notes.append("SHACL validation unavailable; data completeness assumed at 0.85.")
        degraded.append("shacl_validation")
    else:
        data = shacl.completeness
        if shacl.conforms:
            notes.append(
                f"All {shacl.nodes_validated} validated records conform to the "
                f"ontology's SHACL shapes."
            )
        else:
            notes.append(
                f"{len(shacl.violations)} of {shacl.nodes_validated} records violate "
                f"a SHACL shape ({', '.join(f'{k}:{v}' for k, v in shacl.by_shape.items())})."
            )

    # A traversal that reads fields which are empty in the source is less
    # trustworthy than one whose inputs are all populated.
    missing = 0
    checked = 0
    for m in traversal.materials:
        checked += 2
        if m.unit_cost <= 0:
            missing += 1
        if m.on_hand_qty < 0:
            missing += 1
    for d in traversal.deliveries:
        checked += 1
        if d.order_value <= 0:
            missing += 1
    if checked:
        field_completeness = 1.0 - (missing / checked)
        if missing:
            notes.append(
                f"{missing} of {checked} numeric inputs on the traversal path were "
                f"absent or non-positive in the source records."
            )
        data = min(data, (data + field_completeness) / 2)

    # ---- traversal coverage -------------------------------------------
    coverage = traversal.hop_coverage
    if traversal.hops_failed:
        notes.append(
            f"Incomplete traversal: {len(traversal.hops_completed)} of "
            f"{len(traversal.hops_completed) + len(traversal.hops_failed)} hops "
            f"completed (failed: {', '.join(traversal.hops_failed)})."
        )
        degraded.append("graph_traversal")
    else:
        notes.append(f"All {len(traversal.hops_completed)} traversal hops completed.")

    # ---- engine agreement ---------------------------------------------
    if cross is None:
        agreement = 1.0
    else:
        agreement = cross.agreement
        notes.extend(cross.notes)
        if cross.discrepancies:
            degraded.append("llm_cross_check")

    if not llm_available:
        degraded.append("llm_narrative")
        notes.append(
            "No LLM configured: figures, impact and mitigation are complete; "
            "only the prose summary is absent."
        )
    if graph_backend_name == "memory":
        notes.append(
            "Graph served from the in-process backend (no Neo4j credentials); "
            "results are identical to the Neo4j path."
        )

    overall = (
        max(data, 1e-6) ** _W["data"]
        * max(coverage, 1e-6) ** _W["coverage"]
        * max(agreement, 1e-6) ** _W["agreement"]
    )

    return ConfidenceScore(
        overall=round(min(1.0, overall), 4),
        data_completeness=round(min(1.0, data), 4),
        traversal_coverage=round(min(1.0, coverage), 4),
        engine_agreement=round(min(1.0, agreement), 4),
        formula=FORMULA, notes=notes, degraded_modes=degraded,
    )
