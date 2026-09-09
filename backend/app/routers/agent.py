"""Agentic entry point.

Unlike /api/query -- which parses a question into parameters for one fixed
pipeline -- this endpoint lets the model choose which graph questions to ask and
in what order, and returns the trajectory it took. The deterministic pipeline is
still the only thing that produces money: it is reachable here as a tool.

This endpoint is the one capability that genuinely requires an LLM, so it is
also the one that returns 503 without one. /api/impact is unaffected.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent import AgentUnavailable, Trajectory, run_agent
from app.models import ImpactReport

router = APIRouter(tags=["agent"])


class AgentRequest(BaseModel):
    question: str = Field(min_length=3, description="A supply-chain question in plain language")


class CrossCheckSummary(BaseModel):
    """Whether every monetary figure in the answer traces to a computed one."""

    agreement: float
    checked: int
    matched: int
    discrepancies: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    answer: str
    trajectory: Trajectory
    # Present whenever the run called supplier_delay_impact, so the console can
    # render its usual panels over the identical report /api/impact would give.
    report: ImpactReport | None = None
    cross_check: CrossCheckSummary | None = None


@router.post("/agent", response_model=AgentResponse)
def agent(req: AgentRequest, request: Request) -> AgentResponse:
    try:
        result = run_agent(
            request.app.state.backend,
            question=req.question,
            shacl_report=getattr(request.app.state, "shacl_report", None),
        )
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    cross = None
    if result.cross_check is not None:
        c = result.cross_check
        cross = CrossCheckSummary(
            agreement=round(c.agreement, 4), checked=c.checked, matched=c.matched,
            discrepancies=[{
                "stated": d.stated, "nearest_computed": d.nearest_computed,
                "relative_error": d.relative_error, "context": d.context,
            } for d in c.discrepancies],
            notes=c.notes,
        )

    return AgentResponse(
        answer=result.answer, trajectory=result.trajectory,
        report=result.report, cross_check=cross,
    )
