"""Supplier delay impact analysis."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.engines.deterministic import DEFAULT_HORIZON_DAYS, SupplierNotFound
from app.engines.orchestrator import analyse
from app.models import ImpactReport

router = APIRouter(tags=["impact"])


class ImpactRequest(BaseModel):
    supplier_id: str = Field(description="LFA1.LIFNR of the delayed supplier")
    delay_days: int = Field(default=14, ge=1, le=365)
    horizon_days: int = Field(default=DEFAULT_HORIZON_DAYS, ge=1, le=730)
    include_narrative: bool = Field(
        default=True, description="Request LLM prose. Ignored when no LLM is configured."
    )
    as_of: date | None = None


@router.post("/impact", response_model=ImpactReport)
def impact(req: ImpactRequest, request: Request) -> ImpactReport:
    try:
        return analyse(
            request.app.state.backend,
            supplier_id=req.supplier_id,
            delay_days=req.delay_days,
            horizon_days=max(req.horizon_days, req.delay_days + 1),
            as_of=req.as_of,
            include_narrative=req.include_narrative,
            shacl_report=getattr(request.app.state, "shacl_report", None),
        )
    except SupplierNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
