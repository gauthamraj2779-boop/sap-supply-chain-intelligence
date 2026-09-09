"""Avoidance planning: feasible, costed, non-redundant, and cheapest-first."""

from app.engines.avoidance import attribute_exposure, find_actions
from app.engines.deterministic import run_traversal
from app.engines.financial import compute_exposure
from tests.conftest import DELAY, TOSHIRO


def test_finds_multiple_high_roi_actions(plan):
    assert len(plan.actions) >= 2
    payers = [a for a in plan.actions if a.cost > 0]
    assert payers, "expected at least one costed action"
    assert all(a.roi > 1 for a in payers), "a costed action must return more than it costs"


def test_mitigates_most_of_the_exposure(plan):
    assert plan.mitigation_pct > 0.80
    assert plan.exposure_after < plan.exposure_before
    assert plan.total_avoidance_cost < plan.total_risk_mitigated


def test_alternate_supplier_beats_the_delay(plan):
    """An alternate source is only a rescue if it arrives before the delayed goods."""
    alts = [a for a in plan.actions if a.kind == "alternate_supplier"]
    assert alts, "Nova is an approved MCU-32 source and should be found"
    for a in alts:
        assert a.lead_time_days < DELAY


def test_no_duplicate_or_double_counted_actions(plan):
    titles = [a.title for a in plan.actions]
    assert len(titles) == len(set(titles)), "same action proposed twice"
    deferrals = [a.title for a in plan.actions if a.kind == "production_resequence"]
    assert len(deferrals) == len(set(deferrals)), "same order deferred twice"


def test_never_claims_more_than_the_exposure(plan, exposure):
    assert plan.total_risk_mitigated <= exposure.total_financial_exposure + 0.01
    assert plan.exposure_after >= 0


def test_chooses_the_cheapest_source_of_coverage(plan):
    """A rejected option must be more expensive per unit than what was chosen."""
    chosen_rates = [a.cost / a.qty_covered for a in plan.actions if a.qty_covered]
    for r in plan.considered_but_rejected:
        assert r.unit_cost >= min(chosen_rates), (
            "a cheaper option was rejected in favour of a dearer one"
        )


def test_rejected_options_explain_themselves(plan):
    for r in plan.considered_but_rejected:
        assert r.reason and "/unit" in r.reason
        assert r.summary


def test_never_defers_an_order_a_customer_is_waiting_on(plan, traversal):
    """Deferring an order that feeds a customer commitment would move the
    problem, not solve it."""
    committed = {so.matnr for so in traversal.sales_orders}
    for a in plan.actions:
        if a.kind == "production_resequence":
            aufnr = a.title.split()[3]
            po = next(p for p in traversal.production_orders if p.aufnr == aufnr)
            assert po.output_matnr not in committed


def test_never_raids_a_plant_that_needs_the_stock(backend, plan):
    for a in plan.actions:
        if a.kind != "cross_plant_transfer":
            continue
        source_werks = a.title.split("plant ")[-1].strip()
        local = sum(r["BDMNG"] for r in backend.reservations_for(a.target_matnr, source_werks))
        stock = backend.stock(a.target_matnr, source_werks)
        assert stock["LABST"] - local >= a.qty_covered


def test_every_action_cites_sap_evidence(plan):
    sap_tables = ("EINA", "EINE", "MARD", "MARC", "RESB", "AFKO", "VBAP", "LFA1")
    for a in plan.actions:
        assert a.evidence, f"{a.title} has no evidence"
        assert any(t in e for e in a.evidence for t in sap_tables)


def test_attribution_never_exceeds_total(traversal, exposure):
    attributed = sum(attribute_exposure(traversal, exposure).values())
    assert attributed <= exposure.total_financial_exposure * 1.01


def test_no_actions_proposed_when_there_is_no_problem(backend):
    t = run_traversal(backend, TOSHIRO, DELAY)
    e = compute_exposure(t, backend)
    p = find_actions(backend, t, e)
    assert p.actions == []
    assert p.total_avoidance_cost == 0.0
