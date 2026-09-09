"""Natural-language entry point.

Parses the question into impact parameters, then runs the identical
deterministic pipeline as /api/impact. The parse works with or without an LLM,
and the response always reports which parser produced the parameters.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.engines.deterministic import SupplierNotFound
from app.engines.generative import translate_query
from app.engines.orchestrator import analyse
from app.graph.adapter import GraphUnavailable
from app.models import ImpactReport

router = APIRouter(tags=["query"])

EXAMPLES = [
    "Supplier Apex Microelectronics is delayed by 14 days. What's our exposure?",
    "What if we lose our sole source for MCU-32 microcontrollers for 21 days?",
    "Toshiro Metals slipped 10 days - what is the impact over the next 60 days?",
    "How exposed are we if Nova Components is 7 days late?",
]


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    include_narrative: bool = True


class QueryResponse(BaseModel):
    question: str
    interpreted: dict
    report: ImpactReport | None = None
    error: str | None = None


class CypherRequest(BaseModel):
    query: str = Field(min_length=6)


@router.get("/query/examples")
def examples() -> dict:
    return {"examples": EXAMPLES}


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    backend = request.app.state.backend
    parsed = translate_query(req.question, backend.suppliers(), backend)

    if not parsed.get("supplier_id"):
        return QueryResponse(
            question=req.question, interpreted=parsed,
            error=("Could not identify a supplier in the question. Name a supplier, "
                   "give its LIFNR, or name a material and its primary source will "
                   "be resolved. See GET /api/query/examples."),
        )

    try:
        report = analyse(
            backend,
            supplier_id=parsed["supplier_id"],
            delay_days=parsed["delay_days"],
            horizon_days=parsed["horizon_days"],
            include_narrative=req.include_narrative,
            shacl_report=getattr(request.app.state, "shacl_report", None),
        )
    except SupplierNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return QueryResponse(question=req.question, interpreted=parsed, report=report)


@router.post("/cypher")
def cypher(req: CypherRequest, request: Request) -> dict:
    """Read-only Cypher escape hatch. Neo4j backend only."""
    backend = request.app.state.backend
    try:
        return {"rows": backend.run_cypher(req.query), "backend": backend.name}
    except GraphUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
