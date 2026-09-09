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
    assert not c.available
    assert c.complete("s", "u") is None
    assert c.complete_json("s", "u", {"type": "object"}) is None


@pytest.mark.parametrize("provider", ["openai", "deepseek", "groq", "azure", "gemini", "none"])
def test_every_provider_degrades_cleanly(provider):
    c = LLMClient(Settings(llm_provider=provider))
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
    """'$95.6M' is a legitimate way to write 95,552,000, not a hallucination."""
    result = verify_narrative("Exposure is about $95.6M.", exposure, traversal, plan)
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
