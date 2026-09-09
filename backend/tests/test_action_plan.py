"""The LLM action plan writer.

The engine's numbers are the record. These tests assert that generated prose is
additive, is thrown away the moment it disagrees with a computed figure, and
that its absence changes nothing.

The stub below stands in for the provider so the *checking* is what is under
test; nothing it returns ever reaches a report field other than ``narrative``.
"""

from app.engines import generative
from app.engines.generative import _unsupported_measure, write_action_plan
from app.engines.llm import LLMStatus


class StubLLM:
    """A provider that returns exactly the narratives a test wants to check."""

    def __init__(self, narratives):
        self._narratives = narratives
        self.available = True

    def status(self):
        return LLMStatus(provider="stub", model="stub-1", available=True, reason="ready")

    def complete_json(self, system, user, schema, max_tokens=800):
        return {"narratives": self._narratives}


def _install(monkeypatch, narratives):
    stub = StubLLM(narratives)
    monkeypatch.setattr(generative, "get_llm", lambda: stub)
    return stub


def test_no_llm_leaves_every_action_on_its_computed_text(plan, traversal, exposure):
    fresh = plan.model_copy(deep=True)
    write_action_plan(fresh, traversal, exposure)

    assert all(a.narrative is None for a in fresh.actions)
    assert all(a.title and a.description for a in fresh.actions)
    assert "unavailable" in fresh.narrative_source


def test_faithful_prose_is_attached_beside_the_computed_action(
    monkeypatch, plan, traversal, exposure
):
    fresh = plan.model_copy(deep=True)
    a = fresh.actions[0]
    _install(monkeypatch, [{
        "index": 0,
        "narrative": (
            f"Move {a.qty_covered:,.0f} units of {a.target_matnr} to the approved "
            f"alternate source. The switch costs {a.cost:,.0f} USD and removes "
            f"{a.risk_mitigated:,.0f} USD of exposure, arriving in "
            f"{a.lead_time_days:,.0f} days."
        ),
    }])

    write_action_plan(fresh, traversal, exposure)

    assert fresh.actions[0].narrative
    assert fresh.narrative_source == "stub:stub-1"
    # The prose is an addition, never a substitution.
    assert fresh.actions[0].title == plan.actions[0].title
    assert fresh.actions[0].description == plan.actions[0].description
    assert fresh.actions[0].cost == plan.actions[0].cost
    assert fresh.actions[0].risk_mitigated == plan.actions[0].risk_mitigated
    assert fresh.actions[0].roi == plan.actions[0].roi


def test_a_rephrased_cost_is_discarded_and_recorded(
    monkeypatch, plan, traversal, exposure
):
    fresh = plan.model_copy(deep=True)
    a = fresh.actions[0]
    _install(monkeypatch, [{
        "index": 0,
        "narrative": (
            f"Re-sourcing {a.target_matnr} costs roughly 195,000 USD and removes "
            f"{a.risk_mitigated:,.0f} USD of exposure."
        ),
    }])

    write_action_plan(fresh, traversal, exposure)

    assert fresh.actions[0].narrative is None, "prose that restates a figure is dropped"
    assert fresh.actions[0].cost == plan.actions[0].cost
    assert any("discarded" in n and "195,000" in n for n in fresh.narrative_notes)
    assert any("0 of 1" in n for n in fresh.narrative_notes)


def test_a_rewritten_quantity_is_discarded(monkeypatch, plan, traversal, exposure):
    """Quantities carry no currency marker, so they are checked separately."""
    fresh = plan.model_copy(deep=True)
    a = fresh.actions[0]
    _install(monkeypatch, [{
        "index": 0,
        "narrative": (
            f"Re-source 9,400 units of {a.target_matnr}, at a cost of "
            f"{a.cost:,.0f} USD."
        ),
    }])

    write_action_plan(fresh, traversal, exposure)

    assert fresh.actions[0].narrative is None
    assert fresh.actions[0].qty_covered == plan.actions[0].qty_covered
    assert any("9,400" in n for n in fresh.narrative_notes)


def test_one_bad_narrative_does_not_cost_the_others(
    monkeypatch, plan, traversal, exposure
):
    fresh = plan.model_copy(deep=True)
    good, bad = fresh.actions[0], fresh.actions[1]
    _install(monkeypatch, [
        {"index": 0, "narrative": (
            f"Switching source costs {good.cost:,.0f} USD and removes "
            f"{good.risk_mitigated:,.0f} USD of exposure.")},
        {"index": 1, "narrative": (
            f"Deferring {bad.title.split()[3]} frees the material at no cost and "
            f"removes 61,000,000 USD of exposure.")},
    ])

    write_action_plan(fresh, traversal, exposure)

    assert fresh.actions[0].narrative
    assert fresh.actions[1].narrative is None
    assert any("1 of 2" in n for n in fresh.narrative_notes)


def test_unsupported_measure_accepts_the_figures_the_model_was_given(plan, traversal):
    a = plan.actions[0]
    ok = (f"Covers {a.qty_covered:,.0f} units within {a.lead_time_days:,.0f} days, "
          f"against a {traversal.delay_days}-day delay.")
    assert _unsupported_measure(ok, a, traversal) is None
    assert _unsupported_measure("Covers 12,345 units.", a, traversal) == 12_345.0


def test_report_carries_action_narratives_as_null_without_an_llm(backend):
    from app.engines.orchestrator import analyse
    from tests.conftest import APEX, DELAY

    report = analyse(backend, APEX, DELAY)
    assert report.avoidance.actions
    assert all(a.narrative is None for a in report.avoidance.actions)
    assert report.avoidance.narrative_notes == []
