"""Agent loop and tool surface.

The tools run for real against the in-process graph -- every assertion below is
about data the handlers actually read. What is scripted is the *model*, because
the suite is hermetic (conftest pins LLM_PROVIDER=none) and because a live model
cannot be made to reproduce a step cap or an empty answer on demand.
"""

import pytest
from fastapi.testclient import TestClient


def deterministic_total() -> float:
    """The exposure the engines compute for the flagship scenario, right now.

    Derived rather than pinned: hand-computed constants belong in
    test_financial.py, which owns the arithmetic. These tests only care that the
    agent surfaces the engine's number without altering it, so a legitimate
    change to the model (the BOM cascade, for one) must not fail them here.
    """
    from app.engines.orchestrator import analyse
    from app.graph.backends.memory import MemoryBackend

    backend = MemoryBackend()
    backend.connect()
    try:
        return analyse(
            backend, "0000001000", 14, include_narrative=False
        ).financial_exposure.total_financial_exposure
    finally:
        backend.close()


from app.agent import loop as agent_loop
from app.agent import tools as T
from app.agent.loop import AgentUnavailable, run_agent
from app.engines.llm import LLMStatus, ToolCall, ToolTurn
from app.engines.orchestrator import analyse
from app.main import app

from .conftest import APEX, DELAY


# --------------------------------------------------------------------------
# A scripted model. Real tools, real results; only the choices are canned.
# --------------------------------------------------------------------------
class ScriptedLLM:
    """Replays a list of turns, then repeats the last one forever."""

    available = True
    supports_tools = True

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = 0

    def status(self):
        return LLMStatus(provider="scripted", model="scripted-1",
                         available=True, reason="ready")

    def complete_with_tools(self, messages, tools=None, max_tokens=1200):
        self.calls += 1
        # No tools offered means "answer now": the loop's forced close-out.
        if tools is None:
            return _say("Answering with what the tools returned.")
        turn = self.turns[min(self.calls - 1, len(self.turns) - 1)]
        return turn


def _say(text):
    return ToolTurn(content=text, tool_calls=[],
                    assistant_message={"role": "assistant", "content": text},
                    finish_reason="stop")


def _call(name, args, cid="c1", content=None):
    return ToolTurn(
        content=content,
        tool_calls=[ToolCall(id=cid, name=name, arguments=args, raw_arguments="{}")],
        assistant_message={"role": "assistant", "content": content or "",
                           "tool_calls": [{"id": cid, "type": "function",
                                           "function": {"name": name, "arguments": "{}"}}]},
        finish_reason="tool_calls",
    )


# --------------------------------------------------------------------------
# Tools: real handlers over the real graph
# --------------------------------------------------------------------------
def test_ontology_tool_publishes_the_real_label_vocabulary(backend):
    r = T.execute("get_ontology_schema", {}, backend)
    assert r.ok
    labels = {n["label"] for n in r.data["node_types"]}
    assert {"Supplier", "Material", "Delivery", "Customer"} <= labels
    assert all(n["source_tables"] for n in r.data["node_types"])
    assert r.data["blast_radius_hops"][0] == "supplier"


def test_find_suppliers_filters_on_the_real_country_key(backend):
    r = T.execute("find_suppliers", {"country": "tw"}, backend)
    assert r.ok and r.sap_tables == ["LFA1"]
    assert [s["LIFNR"] for s in r.data["suppliers"]] == [APEX]
    assert T.execute("find_suppliers", {"country": "ZZ"}, backend).data["count"] == 0


def test_supplier_delay_impact_is_the_impact_pipeline_verbatim(backend):
    """The agent's money must be the same money /api/impact serves."""
    r = T.execute("supplier_delay_impact",
                  {"supplier_id": APEX, "delay_days": DELAY}, backend)
    assert r.ok and r.report is not None

    truth = analyse(backend, supplier_id=APEX, delay_days=DELAY,
                    include_narrative=False)
    assert (r.report.financial_exposure.total_financial_exposure
            == truth.financial_exposure.total_financial_exposure)
    assert (r.data["financial_exposure"]["total"]
            == truth.financial_exposure.total_financial_exposure)
    # The safety machinery travels with the report, not around it.
    assert r.report.financial_exposure.assumptions
    assert r.report.confidence.formula
    assert r.report.avoidance.actions


def test_impact_tool_attributes_only_the_hops_that_completed(backend):
    r = T.execute("supplier_delay_impact",
                  {"supplier_id": APEX, "delay_days": DELAY}, backend)
    assert r.report.traversal.hops_failed == []
    # Full traversal -> the tables of every hop, in traversal order.
    assert r.sap_tables[:4] == ["LFA1", "EKKO", "EKPO", "EKET"]
    assert {"MARD", "RESB", "VBAP", "LIKP", "KNA1"} <= set(r.sap_tables)


def test_impact_tool_rejects_an_unknown_supplier_without_raising(backend):
    r = T.execute("supplier_delay_impact",
                  {"supplier_id": "9999999999", "delay_days": 5}, backend)
    assert not r.ok and "find_suppliers" in r.error


def test_stock_reservation_and_source_tools_read_real_records(backend):
    stock = T.execute("find_material_stock", {"matnr": "MCU-32"}, backend)
    assert stock.ok and stock.data["total_on_hand"] > 0
    assert stock.sap_tables == ["MARA", "MARC", "MARD"]

    plant = stock.data["stock"][0]["WERKS"]
    resb = T.execute("find_reservations", {"matnr": "MCU-32", "werks": plant}, backend)
    assert resb.ok and resb.sap_tables == ["RESB"]
    assert resb.data["total_required_qty"] == sum(
        r["BDMNG"] for r in backend.reservations_for("MCU-32", plant)
    )

    src = T.execute("find_alternate_sources", {"matnr": "MCU-32"}, backend)
    assert src.ok and src.data["count"] == len(backend.alternate_sources("MCU-32", ""))
    assert APEX in {s["LIFNR"] for s in src.data["sources"]}


def test_trace_downstream_reaches_customers(backend):
    aufnr = backend.t["prod_order_header"][0]["AUFNR"]
    r = T.execute("trace_downstream", {"aufnr": aufnr}, backend)
    assert r.ok and r.data["customers"]
    assert r.data["production_order"]["aufnr"] == aufnr
    assert {"AFKO", "VBAP", "LIKP", "KNA1"} <= set(r.sap_tables)


def test_lineage_tool_resolves_to_real_sap_fields(backend):
    r = T.execute("lineage", {"node_type": "Material", "node_id": "MCU-32"}, backend)
    assert r.ok and ("MARD", "LABST") in {
        (f["sap_table"], f["sap_field"]) for f in r.data["fields"]
    }
    bad = T.execute("lineage", {"node_type": "Nonsense", "node_id": "x"}, backend)
    assert not bad.ok and "Unknown node type" in bad.error


@pytest.mark.parametrize("query", [
    "CREATE (n:Supplier) RETURN n",
    "MATCH (n:Supplier) SET n.risk_score = 0 RETURN n",
    "MATCH (n) DETACH DELETE n",
    "MERGE (n:Material {matnr:'X'}) RETURN n",
    "MATCH (n) CALL apoc.export.csv.all('x', {}) RETURN n",
])
def test_cypher_tool_refuses_writes_before_dispatch(backend, query):
    r = T.execute("run_cypher", {"query": query}, backend)
    assert not r.ok and "Refused" in r.error


def test_cypher_tool_is_not_offered_without_a_cypher_backend(backend):
    assert backend.supports_cypher is False
    assert "run_cypher" not in {s["function"]["name"] for s in T.tool_specs(backend)}
    r = T.execute("run_cypher", {"query": "MATCH (n) RETURN n LIMIT 1"}, backend)
    assert not r.ok and "GRAPH_BACKEND=neo4j" in r.error


def test_bad_tool_names_and_arguments_come_back_as_results_not_exceptions(backend):
    assert not T.execute("teleport", {}, backend).ok
    bad = T.execute("find_reservations", {"matnr": "MCU-32"}, backend)
    assert not bad.ok and "Bad arguments" in bad.error


# --------------------------------------------------------------------------
# Loop
# --------------------------------------------------------------------------
def test_loop_terminates_at_the_step_cap_and_still_answers(backend):
    """A model that never stops asking is stopped, and made to conclude."""
    llm = ScriptedLLM([_call("find_material_stock", {"matnr": "MCU-32",
                                                     "reason": "keep looking"})])
    result = run_agent(backend, "Tell me everything", llm=llm)

    assert result.trajectory.step_count == agent_loop.MAX_STEPS
    assert result.trajectory.stopped_because == "step_cap"
    assert result.answer
    assert all(s.ok for s in result.trajectory.steps)
    assert [s.step for s in result.trajectory.steps] == list(range(1, 9))


def test_a_vague_question_ends_with_no_steps_and_says_what_it_lacks(backend):
    llm = ScriptedLLM([_say("I cannot answer that: no supplier, material or "
                            "production order was named.")])
    result = run_agent(backend, "what about the thing", llm=llm)

    assert result.trajectory.steps == []
    assert result.trajectory.stopped_because == "answered"
    assert "no supplier" in result.answer
    assert result.report is None


def test_the_trajectory_records_the_handler_s_tables_not_the_model_s_claim(backend):
    llm = ScriptedLLM([
        _call("find_material_stock",
              {"matnr": "MCU-32", "reason": "Checking stock; this reads VBAK and LIKP."},
              content="thinking aloud"),
        _say("done"),
    ])
    step = run_agent(backend, "How much MCU-32 do we hold?", llm=llm).trajectory.steps[0]

    assert step.sap_tables_touched == ["MARA", "MARC", "MARD"]
    assert "VBAK" not in step.sap_tables_touched
    # The stated reason is the model's own words, and is not a handler argument.
    assert step.thought.startswith("Checking stock")
    assert "reason" not in step.args
    assert step.result is not None and step.duration_ms >= 0


def test_a_run_that_calls_the_impact_tool_carries_the_full_report(backend):
    llm = ScriptedLLM([
        _call("supplier_delay_impact",
              {"supplier_id": APEX, "delay_days": DELAY, "reason": "priced impact"}),
        _say("Exposure is 95,552,000 USD."),
    ])
    result = run_agent(backend, f"What if {APEX} slips {DELAY} days?", llm=llm)

    assert result.report is not None
    assert (result.report.financial_exposure.total_financial_exposure
            == deterministic_total()), (
        "the agent must report the engine's figure, whatever it currently is"
    )
    # The agent's prose passes the same figure gate as the narrator's.
    assert result.cross_check is not None
    assert result.cross_check.checked == 1 and not result.cross_check.discrepancies


def test_a_figure_the_engines_never_computed_is_flagged(backend):
    """The safety property: a bad answer is caught, not absorbed."""
    llm = ScriptedLLM([
        _call("supplier_delay_impact",
              {"supplier_id": APEX, "delay_days": DELAY, "reason": "priced impact"}),
        _say("Exposure is roughly 41,000,000 USD."),
    ])
    result = run_agent(backend, "exposure?", llm=llm)

    assert result.cross_check.discrepancies
    assert (result.report.financial_exposure.total_financial_exposure
            == deterministic_total()), (
        "the agent must report the engine's figure, whatever it currently is"
    )


def test_no_model_means_no_agent_rather_than_an_invented_one(backend):
    class Offline:
        available = False
        supports_tools = False

        def status(self):
            return LLMStatus(provider="none", model=None, available=False,
                             reason="LLM_PROVIDER=none")

    with pytest.raises(AgentUnavailable) as exc:
        run_agent(backend, "anything", llm=Offline())
    assert "/api/impact" in str(exc.value)


# --------------------------------------------------------------------------
# HTTP contract
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_agent_endpoint_503s_without_an_llm_while_impact_still_works(client):
    r = client.post("/api/agent", json={"question": "Which customers are exposed?"})
    assert r.status_code == 503
    assert "/api/impact" in r.json()["detail"]

    # The whole point of the 503: nothing else degrades with it.
    d = client.post("/api/impact", json={"supplier_id": APEX, "delay_days": DELAY})
    assert d.status_code == 200
    assert (d.json()["financial_exposure"]["total_financial_exposure"]
            == deterministic_total())
    assert d.json()["avoidance"]["actions"] and d.json()["confidence"]["formula"]


def test_agent_endpoint_validates_input(client):
    assert client.post("/api/agent", json={}).status_code == 422
    assert client.post("/api/agent", json={"question": "x"}).status_code == 422


def test_health_does_not_claim_agentic_reasoning_without_a_model(client):
    assert client.get("/api/health").json()["capabilities"]["agentic_reasoning"] is False
