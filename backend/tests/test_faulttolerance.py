"""Degradation guarantees.

The system's central claim is that missing or misbehaving components reduce
capability without producing a wrong answer. These tests are that claim.
"""

import pytest

from app.config import Settings
from app.engines.llm import LLMClient
from app.engines.orchestrator import analyse
from app.graph.adapter import GraphUnavailable, build_backend
from app.validation.cross_check import verify_narrative
from tests.conftest import APEX, DELAY


def test_full_report_without_any_llm(backend):
    """No API key at all: every number is still produced."""
    report = analyse(backend, APEX, DELAY)
    assert report.narrative is None
    assert report.financial_exposure.total_financial_exposure > 0
    assert report.traversal.production_orders
    assert report.avoidance and report.avoidance.actions
    assert report.blast_radius_nodes
    assert "llm_narrative" in report.confidence.degraded_modes
    assert report.confidence.overall > 0.9, "absent prose must not gut confidence"


def test_llm_client_never_raises_without_credentials():
    c = LLMClient(Settings(llm_provider="openai", openai_api_key=None))
    assert c.status().provider == "openai"
    assert not c.available
    assert c.complete("s", "u") is None
    assert c.complete_json("s", "u", {"type": "object"}) is None


@pytest.mark.parametrize("provider", ["openai", "deepseek", "groq", "azure", "gemini", "none"])
def test_every_provider_degrades_cleanly(provider):
    # Explicitly blank every credential: Settings reads .env, and a developer
    # machine with real keys would otherwise make this assert the opposite of
    # what it is testing.
    c = LLMClient(Settings(
        llm_provider=provider,
        openai_api_key=None, deepseek_api_key=None, groq_api_key=None,
        gemini_api_key=None, azure_openai_key=None, azure_openai_api_key=None,
        azure_openai_endpoint=None, azure_openai_deployment=None,
    ))
    assert not c.available
    assert c.status().reason
    assert c.complete("s", "u") is None


def test_hallucinated_figures_are_caught_and_overridden(exposure, traversal, plan):
    fake = ("Total exposure is $210,000,000 driven by $150,000,000 of revenue at risk "
            "and a further $40,000,000 in penalties.")
    result = verify_narrative(fake, exposure, traversal, plan)
    assert not result.clean
    assert result.agreement == 0.0
    assert len(result.discrepancies) == 3
    for d in result.discrepancies:
        assert d.relative_error > 0.05
        assert d.nearest_computed is not None


def test_faithful_figures_pass_cross_check(exposure, traversal, plan):
    real = (f"Total exposure is ${exposure.total_financial_exposure:,.0f}, of which "
            f"${exposure.revenue_at_risk:,.0f} is revenue at risk and "
            f"${exposure.penalty_exposure:,.0f} is penalty exposure.")
    result = verify_narrative(real, exposure, traversal, plan)
    assert result.clean
    assert result.agreement == 1.0
    assert result.checked == 3


def test_rounded_figures_are_accepted(exposure, traversal, plan):
    """'$111.2M' is a legitimate way to write 111,174,000, not a hallucination."""
    result = verify_narrative("Exposure is about $111.2M.", exposure, traversal, plan)
    assert result.clean


def test_hallucination_lowers_confidence(backend, exposure, traversal, plan):
    from app.validation import compute_confidence

    bad = verify_narrative("Exposure is $500,000,000.", exposure, traversal, plan)
    good = verify_narrative(None, exposure, traversal, plan)
    c_bad = compute_confidence(traversal, None, bad, "memory", True)
    c_good = compute_confidence(traversal, None, good, "memory", True)
    assert c_bad.overall < c_good.overall
    assert "llm_cross_check" in c_bad.degraded_modes


def test_backend_falls_back_when_neo4j_is_unreachable():
    """A dead database degrades to the in-process graph rather than a 500."""
    b = build_backend(Settings(
        graph_backend="neo4j",
        neo4j_uri="neo4j+s://does-not-exist.databases.neo4j.io",
        neo4j_password="wrong",
    ))
    assert b.name == "memory"
    assert sum(b.counts().values()) > 0


def test_memory_backend_refuses_cypher_with_a_useful_message(backend):
    with pytest.raises(GraphUnavailable, match="GRAPH_BACKEND=neo4j"):
        backend.run_cypher("MATCH (n) RETURN n")


def test_partial_traversal_lowers_coverage_not_correctness(backend):
    from app.validation import compute_confidence

    report = analyse(backend, APEX, DELAY)
    t = report.traversal
    t.hops_failed = ["deliveries"]
    c = compute_confidence(t, None, None, "memory", False)
    assert c.traversal_coverage < 1.0
    assert "graph_traversal" in c.degraded_modes
    t.hops_failed = []


def test_cross_check_ignores_numbers_that_are_not_money(exposure, traversal, plan):
    """Prose is full of non-monetary numbers.

    Plant codes, quantities, order numbers, day counts and percentages must not
    be read as currency. Flagging those produced false hallucination reports,
    which is worse than no check at all: it condemns a faithful narrative and
    teaches the reader to ignore the warning.
    """
    faithful = (
        f"Total exposure is {exposure.total_financial_exposure:,.0f} USD. "
        "Plant 1010 is short 2,850 units of MCU-32 and 200 units of PWR-IC-7, "
        "while Plant 1020 is short 900 units. Defer production order 000009002 "
        "for FCB-100. Delivery 0080001 is 12 days late. This removes 94.0 percent "
        "of the exposure over 45 days."
    )
    result = verify_narrative(faithful, exposure, traversal, plan)
    assert result.clean, [
        (d.stated, d.context) for d in result.discrepancies
    ]
    assert result.checked == 1, "only the marked USD figure should be checked"


def test_cross_check_still_catches_a_marked_wrong_figure(exposure, traversal, plan):
    """Tightening the extractor must not blunt it."""
    result = verify_narrative(
        "Plant 1010 is short 2,850 units. Total exposure is $500,000,000.",
        exposure, traversal, plan,
    )
    assert not result.clean
    assert len(result.discrepancies) == 1
    assert result.discrepancies[0].stated == 500_000_000


def test_cross_check_accepts_common_money_notations(exposure, traversal, plan):
    from app.validation.cross_check import _extract

    total = exposure.total_financial_exposure
    for text in (f"${total:,.0f}", f"{total:,.0f} USD", f"USD {total:,.0f}", "$95.6M"):
        assert _extract(text), f"failed to read {text!r} as money"


def test_cross_check_ignores_numbers_glued_to_identifiers():
    from app.validation.cross_check import _extract

    assert _extract("order 000009002 and part PWR-IC-7 and SO 0004502-10") == []
