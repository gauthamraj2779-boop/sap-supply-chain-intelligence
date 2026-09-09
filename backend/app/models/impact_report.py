"""Response models.

Every monetary field in here is populated exclusively by
``app.engines.financial``. No LLM output is ever written into these fields --
see ``app.validation.cross_check`` for the enforcement.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Severity = Literal["none", "low", "medium", "high", "critical"]


# --------------------------------------------------------------------------
# Lineage -- every number traceable to an SAP table cell
# --------------------------------------------------------------------------
class LineageStep(BaseModel):
    sap_table: str = Field(description="SAP table name, e.g. 'EKPO'")
    sap_field: str = Field(description="SAP field name, e.g. 'NETWR'")
    key: str = Field(description="Record key, e.g. 'EBELN=4500012/EBELP=10'")
    value: str = Field(description="Value as found in the record")
    meaning: str = Field(description="Business meaning of this field")


class LineageTrail(BaseModel):
    subject: str
    steps: list[LineageStep] = Field(default_factory=list)
    derivation: str | None = Field(
        default=None, description="Arithmetic that produced the derived figure"
    )


# --------------------------------------------------------------------------
# Affected entities, hop by hop
# --------------------------------------------------------------------------
class AffectedPurchaseOrder(BaseModel):
    ebeln: str
    ebelp: str
    matnr: str
    material_name: str
    werks: str
    menge: float
    net_value: float
    original_delivery_date: date
    delayed_delivery_date: date
    delay_days: int
    lineage: LineageTrail


class AffectedMaterial(BaseModel):
    matnr: str
    material_name: str
    werks: str
    plant_name: str
    on_hand_qty: float
    other_inbound_qty: float
    required_qty: float
    shortfall_qty: float
    unit_cost: float
    daily_consumption: float
    days_of_coverage: float
    gap_days: float
    stockout_date: date | None
    severity: Severity
    lineage: LineageTrail


class AffectedProductionOrder(BaseModel):
    aufnr: str
    output_matnr: str
    output_material_name: str
    werks: str
    plant_name: str
    order_qty: float
    scheduled_finish: date
    projected_finish: date
    halt_days: float
    blocking_materials: list[str]
    severity: Severity
    lineage: LineageTrail


class AffectedSalesOrder(BaseModel):
    vbeln: str
    posnr: str
    kunnr: str
    customer_name: str
    matnr: str
    order_qty: float
    net_value: float
    severity: Severity
    lineage: LineageTrail


class AffectedDelivery(BaseModel):
    vbeln: str
    kunnr: str
    customer_name: str
    ref_sales_order: str
    planned_goods_issue: date
    projected_goods_issue: date
    days_late: float
    order_value: float
    penalty_rate: float
    penalty_amount: float
    severity: Severity
    lineage: LineageTrail


# --------------------------------------------------------------------------
# Financial roll-up
# --------------------------------------------------------------------------
class CustomerExposure(BaseModel):
    kunnr: str
    customer_name: str
    revenue_at_risk: float
    penalty_exposure: float
    total_exposure: float
    deliveries_at_risk: int


class FinancialExposure(BaseModel):
    po_stranded_value: float = Field(description="Open PO commitments now at risk (EKPO.NETWR)")
    production_halt_cost: float = Field(description="idle_plant_cost_per_day x halt_days")
    revenue_at_risk: float = Field(description="Downstream sales order value (VBAP.NETWR)")
    penalty_exposure: float = Field(description="Contractual late-delivery penalties")
    total_financial_exposure: float

    by_customer: list[CustomerExposure] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Non-SAP figures used in the calculation, stated explicitly",
    )

    @computed_field
    @property
    def components_reconcile(self) -> bool:
        return self.self_consistent()

    def self_consistent(self, tolerance: float = 0.01) -> bool:
        parts = (
            self.po_stranded_value
            + self.production_halt_cost
            + self.revenue_at_risk
            + self.penalty_exposure
        )
        return abs(parts - self.total_financial_exposure) <= tolerance


# --------------------------------------------------------------------------
# Confidence -- published components, no black box
# --------------------------------------------------------------------------
class ConfidenceScore(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    data_completeness: float = Field(ge=0.0, le=1.0)
    traversal_coverage: float = Field(ge=0.0, le=1.0)
    engine_agreement: float = Field(ge=0.0, le=1.0)
    formula: str
    notes: list[str] = Field(default_factory=list)
    degraded_modes: list[str] = Field(
        default_factory=list, description="Which subsystems were unavailable or partial"
    )


TimelineKind = Literal[
    "trigger", "purchase_order", "material", "production", "delivery"
]


class TimelineEvent(BaseModel):
    day_offset: int
    event_date: date
    label: str
    detail: str
    cumulative_exposure: float
    kind: TimelineKind = "trigger"


# --------------------------------------------------------------------------
# Traversal + top-level report
# --------------------------------------------------------------------------
class TraversalResult(BaseModel):
    supplier_id: str
    supplier_name: str
    delay_days: int
    as_of_date: date

    purchase_orders: list[AffectedPurchaseOrder] = Field(default_factory=list)
    materials: list[AffectedMaterial] = Field(default_factory=list)
    production_orders: list[AffectedProductionOrder] = Field(default_factory=list)
    sales_orders: list[AffectedSalesOrder] = Field(default_factory=list)
    deliveries: list[AffectedDelivery] = Field(default_factory=list)
    plants: list[str] = Field(default_factory=list)
    customers: list[str] = Field(default_factory=list)

    hops_completed: list[str] = Field(default_factory=list)
    hops_failed: list[str] = Field(default_factory=list)

    @property
    def hop_coverage(self) -> float:
        total = len(self.hops_completed) + len(self.hops_failed)
        return 1.0 if total == 0 else len(self.hops_completed) / total


class GraphNode(BaseModel):
    id: str
    label: str
    caption: str
    severity: Severity = "none"
    exposure: float = 0.0
    properties: dict = Field(default_factory=dict)
    sap_table: str = Field(default="", description="SAP table(s) this node derives from")
    sap_fields: dict = Field(
        default_factory=dict,
        description="Raw SAP field/value pairs behind this node, for the lineage inspector",
    )
    lineage: LineageTrail | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    derived_from: str | None = None


class SupplierInfo(BaseModel):
    lifnr: str
    name: str
    country: str | None = None
    risk_score: float | None = None
    sole_source_materials: list[str] = Field(
        default_factory=list,
        description="Materials for which this supplier is the only approved source",
    )


class AffectedCounts(BaseModel):
    purchase_orders: int = 0
    materials: int = 0
    materials_short: int = 0
    plants: int = 0
    production_orders: int = 0
    sales_orders: int = 0
    deliveries: int = 0
    customers: int = 0


class ImpactReport(BaseModel):
    supplier_id: str
    supplier_name: str
    supplier: SupplierInfo
    delay_days: int
    as_of_date: date

    affected_counts: AffectedCounts
    time_to_impact_days: int | None = Field(
        default=None,
        description="Days until the first material stockout; None when nothing goes short",
    )
    critical_path: LineageTrail | None = Field(
        default=None,
        description="Lineage for the single largest exposure, supplier through to customer",
    )

    headline: str
    financial_exposure: FinancialExposure
    traversal: TraversalResult
    timeline: list[TimelineEvent] = Field(default_factory=list)

    avoidance: "AvoidancePlan | None" = None

    confidence: ConfidenceScore
    narrative: str | None = Field(
        default=None, description="LLM prose. None when no LLM is configured or reachable."
    )
    narrative_source: str = "unavailable"

    blast_radius_nodes: list[GraphNode] = Field(default_factory=list)
    blast_radius_edges: list[GraphEdge] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)


from app.models.avoidance_plan import AvoidancePlan  # noqa: E402

ImpactReport.model_rebuild()
