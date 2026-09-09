"""Traversal correctness, verified against hand-computed values.

The numbers below were worked out by hand from the generated CSV/JSON records.
If the engine drifts, these fail -- which is the point: the headline figure has
to be defensible under questioning, not merely reproducible.
"""

from datetime import timedelta

from app.engines.deterministic import run_traversal
from tests.conftest import APEX, DELAY, TOSHIRO


def test_all_eight_hops_complete(traversal):
    assert traversal.hops_failed == []
    assert traversal.hop_coverage == 1.0
    for hop in ("supplier", "purchase_orders", "schedule_lines", "materials",
                "plants", "production_orders", "sales_orders", "deliveries",
                "customers"):
        assert hop in traversal.hops_completed


def test_blast_radius_reaches_every_entity_class(traversal):
    assert traversal.purchase_orders, "no POs reached"
    assert traversal.materials, "no materials reached"
    assert len(traversal.plants) >= 2, "delay should cross plant boundaries"
    assert traversal.production_orders, "no production orders reached"
    assert traversal.sales_orders, "no sales orders reached"
    assert traversal.deliveries, "no deliveries reached"
    assert len(traversal.customers) >= 3, "should reach multiple customers"


def test_mcu32_shortfall_matches_hand_calculation(traversal):
    """MARD.LABST=850; RESB.BDMNG 2000+900+800=3700 all due before the revised
    arrival; sole-sourced so other_inbound=0. shortfall = 3700 - 850 = 2850."""
    m = next(m for m in traversal.materials if m.matnr == "MCU-32" and m.werks == "1010")
    assert m.on_hand_qty == 850.0
    assert m.required_qty == 3700.0
    assert m.other_inbound_qty == 0.0, "MCU-32 is sole-sourced from Apex"
    assert m.shortfall_qty == 2850.0
    assert m.severity == "critical"


def test_well_stocked_material_shows_no_shortfall(traversal):
    """CAP-TANT-22: MARD.LABST=5000 against RESB demand of 4800 -> covered."""
    m = next(m for m in traversal.materials if m.matnr == "CAP-TANT-22")
    assert m.on_hand_qty == 5000.0
    assert m.required_qty == 4800.0
    assert m.shortfall_qty == 0.0
    assert m.severity == "none"


def test_halt_days_derive_from_dates_not_guesses(traversal):
    """9001 needs MCU-32 on D+8; the delayed PO now lands D+20. halt = 12 days."""
    po = next(p for p in traversal.production_orders if p.aufnr == "000009001")
    assert po.halt_days == 12.0
    assert "MCU-32" in po.blocking_materials
    assert po.projected_finish == po.scheduled_finish + timedelta(days=12)


def test_stock_allocated_by_requirement_date(traversal):
    """850 units cover part of the earliest order only; later orders get none,
    so their halt is longer-dated but starts later."""
    o1 = next(p for p in traversal.production_orders if p.aufnr == "000009001")
    o3 = next(p for p in traversal.production_orders if p.aufnr == "000009003")
    assert o1.halt_days == 12.0
    assert o3.halt_days == 10.0, "later requirement date -> shorter wait for same arrival"


def test_covered_material_does_not_halt_production(traversal):
    """No production order should be blocked by a material with zero shortfall."""
    covered = {m.matnr for m in traversal.materials if m.shortfall_qty == 0}
    for po in traversal.production_orders:
        assert not (set(po.blocking_materials) & covered)


def test_every_row_carries_sap_lineage(traversal):
    for row in (traversal.purchase_orders + traversal.materials
                + traversal.production_orders + traversal.sales_orders
                + traversal.deliveries):
        assert row.lineage.steps, f"{row} has no lineage"
        assert row.lineage.derivation, f"{row} has no derivation"
        for step in row.lineage.steps:
            assert step.sap_table and step.sap_field and step.key
            assert step.sap_table.isupper() or "/" in step.sap_table


def test_contrast_supplier_reports_no_impact(backend):
    """A well-stocked supplier must come back clean. A system that alarms on
    every supplier is not reasoning."""
    t = run_traversal(backend, TOSHIRO, DELAY)
    assert t.hops_failed == []
    assert t.purchase_orders, "Toshiro does have open POs in the horizon"
    assert all(m.shortfall_qty == 0 for m in t.materials)
    assert t.production_orders == []
    assert t.deliveries == []


def test_longer_delay_never_reduces_impact(backend):
    small = run_traversal(backend, APEX, 5)
    large = run_traversal(backend, APEX, 30)
    assert (sum(m.shortfall_qty for m in large.materials)
            >= sum(m.shortfall_qty for m in small.materials))
    assert len(large.production_orders) >= len(small.production_orders)
