"""Discovery endpoints: what the pipeline worked out, and the evidence for it.

Both endpoints are read-only and cheap. They serve the committed artifacts when
they exist and recompute deterministically in memory when they do not, so the
API answers correctly on a fresh clone without an LLM, a key or a build step.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.discovery import discover as discovery_engine
from app.discovery import profile as profiler

router = APIRouter(tags=["discovery"])


@router.get("/discovery")
def discovery() -> dict:
    """Discovered entities and relationships, with grounded confidence."""
    doc = discovery_engine.load()
    rels = doc.get("relationships", [])
    return {
        **doc,
        "counts": {
            "entities": len(doc.get("entities", [])),
            "relationships": len(rels),
            "inferred_relationships": sum(1 for r in rels if r.get("inferred")),
        },
    }


@router.get("/discovery/profile")
def discovery_profile(
    min_containment: float = Query(
        profiler.REPORT_THRESHOLD, ge=0.0, le=1.0,
        description="Lower bound on the containment ratio to return.",
    ),
) -> dict:
    """The containment matrix and column statistics the discovery rests on."""
    prof = profiler.load()
    pairs = [p for p in prof.get("containment", [])
             if p["containment"] >= min_containment]
    return {
        "generated_at": prof.get("generated_at"),
        "method": prof.get("method", "deterministic"),
        "thresholds": prof.get("thresholds", {}),
        "tables": prof.get("tables", []),
        "columns": prof.get("columns", []),
        "containment": pairs,
        "counts": {
            "columns": len(prof.get("columns", [])),
            "containment_returned": len(pairs),
            "containment_total": len(prof.get("containment", [])),
            "at_or_above_fk_threshold": sum(
                1 for p in prof.get("containment", [])
                if p["containment"] >= profiler.FK_THRESHOLD
            ),
        },
        "note": prof.get("note"),
    }
