"""Health and capability reporting.

Deliberately verbose about *degraded* state: the point of the architecture is
that missing credentials reduce capability without stopping service, so the
health endpoint has to say exactly which capabilities are live.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import get_settings
from app.engines.llm import get_llm

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = get_settings()
    backend = getattr(request.app.state, "backend", None)
    llm = get_llm().status()

    graph_ok = backend is not None
    counts = backend.counts() if graph_ok else {}

    return {
        "status": "ok" if graph_ok else "degraded",
        "graph": {
            "backend": backend.name if graph_ok else None,
            "configured_backend": settings.graph_backend,
            "supports_cypher": backend.supports_cypher if graph_ok else False,
            "records": sum(counts.values()) if counts else 0,
            "detail": counts,
        },
        "llm": {
            "provider": llm.provider, "model": llm.model,
            "available": llm.available, "detail": llm.reason,
        },
        "capabilities": {
            "impact_analysis": graph_ok,
            "financial_quantification": graph_ok,
            "avoidance_planning": graph_ok,
            "natural_language_query": graph_ok,
            "llm_narrative": llm.available,
            # The agent is the one capability that cannot degrade: with no model
            # there is nothing to choose the tools, so /api/agent returns 503.
            "agentic_reasoning": graph_ok and get_llm().supports_tools,
            "raw_cypher": backend.supports_cypher if graph_ok else False,
        },
        "note": (
            "Financial figures are computed deterministically and do not depend on "
            "the LLM. An unavailable LLM removes prose only."
        ),
    }


@router.get("/suppliers")
def suppliers(request: Request) -> list[dict]:
    backend = request.app.state.backend
    return [
        {"lifnr": s["LIFNR"], "name": s.get("NAME1"), "country": s.get("LAND1"),
         "risk_score": s.get("risk_score")}
        for s in backend.suppliers()
    ]
