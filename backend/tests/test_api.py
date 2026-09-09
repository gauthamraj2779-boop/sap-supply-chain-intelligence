"""HTTP contract tests. Run with no credentials of any kind."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_capabilities_honestly(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["graph"]["backend"] == "memory"
    assert h["graph"]["records"] > 0
    caps = h["capabilities"]
    assert caps["impact_analysis"] and caps["financial_quantification"]
    assert caps["avoidance_planning"] and caps["natural_language_query"]
    assert caps["llm_narrative"] is False, "no key configured; must not claim otherwise"


def test_impact_endpoint_returns_a_complete_report(client):
    r = client.post("/api/impact", json={"supplier_id": "0000001000", "delay_days": 14})
    assert r.status_code == 200
    d = r.json()

    fe = d["financial_exposure"]
    assert fe["total_financial_exposure"] == 111_174_000.0
    assert fe["assumptions"]

    t = d["traversal"]
    assert t["hops_failed"] == []
    for key in ("purchase_orders", "materials", "production_orders",
                "sales_orders", "deliveries"):
        assert t[key], f"{key} empty"

    assert d["avoidance"]["actions"]
    assert d["timeline"]
    assert d["blast_radius_nodes"] and d["blast_radius_edges"]
    assert d["confidence"]["formula"]
    assert d["narrative"] is None and "unavailable" in d["narrative_source"]


def test_impact_rejects_unknown_supplier(client):
    r = client.post("/api/impact", json={"supplier_id": "9999999999", "delay_days": 5})
    assert r.status_code == 404


def test_impact_validates_input(client):
    assert client.post("/api/impact", json={"supplier_id": "0000001000",
                                            "delay_days": 0}).status_code == 422
    assert client.post("/api/impact", json={"delay_days": 5}).status_code == 422


def test_natural_language_query_works_without_an_llm(client):
    r = client.post("/api/query", json={
        "question": "Supplier Apex Microelectronics is delayed by 14 days. What's our exposure?"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["interpreted"]["supplier_id"] == "0000001000"
    assert d["interpreted"]["delay_days"] == 14
    assert d["interpreted"]["parsed_by"] == "deterministic"
    assert d["report"]["financial_exposure"]["total_financial_exposure"] > 0


def test_every_documented_example_query_resolves(client):
    for q in client.get("/api/query/examples").json()["examples"]:
        d = client.post("/api/query", json={"question": q}).json()
        assert d["interpreted"]["supplier_id"], f"unparsed example: {q}"
        assert d["report"] is not None


def test_unparseable_query_explains_itself(client):
    d = client.post("/api/query", json={"question": "what is the weather"}).json()
    assert d["report"] is None
    assert "supplier" in d["error"].lower()


def test_cypher_is_refused_on_the_memory_backend(client):
    r = client.post("/api/cypher", json={"query": "MATCH (n) RETURN n LIMIT 1"})
    assert r.status_code == 400
    assert "GRAPH_BACKEND=neo4j" in r.json()["detail"]


def test_graph_schema_and_ontology_are_served(client):
    s = client.get("/api/schema").json()
    assert len(s["node_types"]) >= 10 and len(s["edge_types"]) >= 12
    assert all(n["source_tables"] for n in s["node_types"])

    o = client.get("/api/ontology").json()
    assert "owl:Class" in o["content"] and "sh:NodeShape" in o["content"]
    assert "sap:sourceTable" in o["content"]

    g = client.get("/api/graph").json()
    assert g["counts"]["nodes"] > 0 and g["counts"]["edges"] > 0


def test_governance_report_is_served(client):
    v = client.get("/api/validation").json()
    assert v["available"] is True
    assert v["nodes_validated"] > 0
    assert 0.0 <= v["completeness"] <= 1.0


def test_lineage_resolves_to_real_sap_fields(client):
    d = client.get("/api/lineage/Material/MCU-32").json()
    assert "MARA" in d["source_tables"]
    fields = {(f["sap_table"], f["sap_field"]) for f in d["fields"]}
    assert ("MARD", "LABST") in fields
    assert ("MARA", "MATNR") in fields
    assert client.get("/api/lineage/Nonsense/x").status_code == 404


def test_contrast_supplier_returns_zero_through_the_api(client):
    d = client.post("/api/impact", json={"supplier_id": "0000001002",
                                         "delay_days": 14}).json()
    assert d["financial_exposure"]["total_financial_exposure"] == 0.0
    assert d["avoidance"]["actions"] == []
    assert "No material financial exposure" in d["headline"]


def test_material_named_question_resolves_to_its_source(client):
    """People ask about the part, not the vendor."""
    d = client.post("/api/query", json={
        "question": "What if we lose our sole source for MCU-32 microcontrollers for 21 days?"
    }).json()
    i = d["interpreted"]
    assert i["supplier_id"] == "0000001000"
    assert i["delay_days"] == 21
    assert i["resolved_via_material"]["matnr"] == "MCU-32"
    assert "EINA/EINE" in i["resolved_via_material"]["note"]
    assert d["report"]["financial_exposure"]["total_financial_exposure"] > 0
