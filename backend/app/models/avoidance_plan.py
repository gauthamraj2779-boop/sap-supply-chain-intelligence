"""Avoidance / mitigation models -- the 'self-healing' half of the system."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

ActionKind = Literal[
    "alternate_supplier",
    "safety_stock_transfer",
    "production_resequence",
    "cross_plant_transfer",
]


class AvoidanceAction(BaseModel):
    kind: ActionKind
    title: str
    description: str

    target_matnr: str | None = None
    target_material_name: str | None = None
    target_werks: str | None = None

    qty_covered: float = 0.0
    lead_time_days: float | None = None
    cost: float = Field(description="Cost of taking this action, in currency units")
    risk_mitigated: float = Field(description="Exposure removed by taking this action")

    evidence: list[str] = Field(
        default_factory=list, description="SAP records supporting this action's feasibility"
    )
    sap_source: str = Field(
        default="", description="SAP table(s) this action's feasibility was proven against"
    )

    @computed_field
    @property
    def roi(self) -> float | None:
        if self.cost <= 0:
            # A zero-cost action has unbounded ROI. JSON cannot carry Infinity,
            # so it reports None and the client renders it as "no cost".
            return None
        return (self.risk_mitigated - self.cost) / self.cost

    @computed_field
    @property
    def roi_display(self) -> str:
        if self.cost <= 0:
            return "no cost" if self.risk_mitigated > 0 else "n/a"
        return f"{self.roi:,.0f}x"


class RejectedOption(BaseModel):
    """An option the engine evaluated and did not take, with the reason.

    Showing the road not taken is what separates a decision from an assertion.
    """

    kind: ActionKind
    summary: str
    unit_cost: float
    reason: str


class AvoidancePlan(BaseModel):
    actions: list[AvoidanceAction] = Field(default_factory=list)
    considered_but_rejected: list[RejectedOption] = Field(default_factory=list)

    exposure_before: float
    exposure_after: float
    total_avoidance_cost: float
    total_risk_mitigated: float

    @computed_field
    @property
    def mitigation_pct(self) -> float:
        if self.exposure_before <= 0:
            return 0.0
        return (self.exposure_before - self.exposure_after) / self.exposure_before

    @computed_field
    @property
    def plan_roi(self) -> float | None:
        if self.total_avoidance_cost <= 0:
            return None
        return self.total_risk_mitigated / self.total_avoidance_cost

    def summary_line(self) -> str:
        if not self.actions:
            return "No avoidance actions available for this scenario."
        return (
            f"{len(self.actions)} actions, cost {self.total_avoidance_cost:,.0f}, "
            f"mitigates {self.total_risk_mitigated:,.0f} "
            f"({self.mitigation_pct:.1%} of exposure)"
        )
