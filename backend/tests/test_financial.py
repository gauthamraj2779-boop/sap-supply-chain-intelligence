"""Financial quantification, verified against hand-computed values."""

from app.engines.deterministic import run_traversal
from app.engines.financial import compute_exposure, headline
from tests.conftest import DELAY, TOSHIRO


def test_total_equals_sum_of_components(exposure):
    assert exposure.self_consistent()
    assert exposure.total_financial_exposure == (
        exposure.po_stranded_value + exposure.production_halt_cost
        + exposure.revenue_at_risk + exposure.penalty_exposure
    )


def test_po_stranded_value_hand_calculation(exposure):
    """Apex PO lines on materials that actually go short:
    MCU-32 2500x120=300,000 + PWR-IC-7 1500x85=127,500 + 900x85=76,500 = 504,000.
    The CAP-TANT-22 line (72,000) is excluded: stock covers it, so nothing strands."""
    assert exposure.po_stranded_value == 504_000.0


def test_production_halt_cost_hand_calculation(exposure):
    """Plant 1010: 12 disrupted days x 180,000 = 2,160,000.
    Plant 1020: 12 disrupted days x 145,000 = 1,740,000. Total 3,900,000.

    Unchanged by the BOM explosion: order 9008 (FMS-850) joins plant 1010 with a
    7-day halt, which is inside the 12 days orders 9001 and 9002 already lose
    there. Cost charges the longest halt per plant, so the plant is not billed
    twice for days it is already idle."""
    assert exposure.production_halt_cost == 3_900_000.0


def test_revenue_and_penalty_hand_calculation(exposure):
    """Six sales order items sit directly behind halted orders:
    ACU-500 31.2M + 10.4M, CSM-300 18.7M + 7.0M, NAV-700 12.4M + 5.2M = 84.9M.
    The BOM adds a seventh: FMS-850 consumes FCB-100 (STPO), whose order 9002 is
    halted, so SO 0004520 at 14.6M is exposed too. 84.9M + 14.6M = 99.5M.

    Penalties are order value x contractual rate on each late delivery:
    0080001 31.2M x 8% = 2,496,000; 0080008 10.4M x 8% = 832,000;
    0080002 18.7M x 8% = 1,496,000; 0080009 7.0M x 6% = 420,000;
    0080003 12.4M x 6% = 744,000;   0080010 5.2M x 5% = 260,000;
    and, new with the BOM, 0080006 14.6M x 7% = 1,022,000. Total 7,270,000.

    504,000 stranded + 3,900,000 halt + 99,500,000 revenue + 7,270,000 penalty
    = 111,174,000."""
    assert exposure.revenue_at_risk == 99_500_000.0
    assert exposure.penalty_exposure == 7_270_000.0
    assert exposure.total_financial_exposure == 111_174_000.0


def test_customer_breakdown_reconciles(exposure):
    total = sum(c.total_exposure for c in exposure.by_customer)
    assert abs(total - (exposure.revenue_at_risk + exposure.penalty_exposure)) < 0.01
    assert exposure.by_customer == sorted(
        exposure.by_customer, key=lambda c: -c.total_exposure
    )


def test_every_non_sap_input_is_declared(exposure):
    """Any figure that is not an SAP field must appear in `assumptions`."""
    blob = " ".join(exposure.assumptions).lower()
    assert "idle cost" in blob or "idle_plant_cost" in blob
    assert "penalty" in blob
    assert "worst case" in blob or "unrecognised" in blob
    assert any("not an sap field" in a.lower() for a in exposure.assumptions)


def test_halt_cost_does_not_double_count_concurrent_orders(exposure, traversal):
    """Three orders halt at plant 1010; charging each would triple-bill the same
    idle days. Cost must reflect the longest halt, not the sum."""
    p1010 = [p for p in traversal.production_orders if p.werks == "1010"]
    assert len(p1010) >= 2, "fixture should have concurrent halts to test against"
    naive_sum = sum(p.halt_days for p in p1010) * 180_000
    assert exposure.production_halt_cost < naive_sum


def test_contrast_supplier_has_zero_exposure(backend):
    t = run_traversal(backend, TOSHIRO, DELAY)
    e = compute_exposure(t, backend)
    assert e.total_financial_exposure == 0.0
    assert "No material financial exposure" in headline(t, e)
