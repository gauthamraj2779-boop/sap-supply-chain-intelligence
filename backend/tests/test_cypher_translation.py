"""Question -> Cypher.

The model writes the query; none of these tests trust it. Every guarantee the
prompt asks for is re-checked in code, and these are those checks.
"""

import pytest
from fastapi.testclient import TestClient

from app.engines.generative import (
    CYPHER_ROW_LIMIT,
    cypher_schema_prompt,
    execute_cypher,
    translate_to_cypher,
    validate_cypher,
)
from app.graph.schema import EDGE_TYPES, NODE_TYPES
from app.main import app
from app.models import CypherTranslation

READ_QUERY = (
    "MATCH (s:Supplier)-[:FULFILLS]->(p:PurchaseOrder)-[:ORDERS]->(m:Material) "
    "WHERE s.lifnr = '0000001000' "
    "RETURN m.matnr AS matnr, sum(p.net_value) AS committed "
    "ORDER BY committed DESC LIMIT 10"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_schema_prompt_is_built_from_the_real_schema():
    prompt = cypher_schema_prompt()
    for label in NODE_TYPES:
        assert f"(:{label})" in prompt
    for edge in EDGE_TYPES:
        assert f"[:{edge.type}]" in prompt
    # Properties, so the model has no reason to invent one.
    assert "lifnr" in prompt and "net_value" in prompt and "shortfall" not in prompt


def test_a_read_query_over_the_schema_passes():
    v = validate_cypher(READ_QUERY)
    assert v.ok and v.reason is None
    assert not v.limit_injected
    assert set(v.labels) == {"Supplier", "PurchaseOrder", "Material"}
    assert set(v.rel_types) == {"FULFILLS", "ORDERS"}


@pytest.mark.parametrize("query, fragment", [
    ("MATCH (s:Supplier) CREATE (n:Supplier {lifnr: 'x'}) RETURN n", "CREATE"),
    ("MERGE (s:Supplier {lifnr: 'x'}) RETURN s", "MERGE"),
    ("MATCH (s:Supplier) DELETE s", "DELETE"),
    ("MATCH (s:Supplier) SET s.name = 'x' RETURN s", "SET"),
    ("MATCH (s:Supplier) REMOVE s.name RETURN s", "REMOVE"),
    ("DROP CONSTRAINT supplier_key", "DROP"),
    ("LOAD CSV FROM 'file:///x.csv' AS row RETURN row", "LOAD CSV"),
    ("MATCH (s:Supplier) CALL db.labels() YIELD label RETURN label", "db."),
    ("MATCH (s:Supplier) CALL apoc.meta.schema() YIELD value RETURN value", "apoc."),
])
def test_mutating_and_administrative_queries_are_refused(query, fragment):
    v = validate_cypher(query)
    assert not v.ok
    assert fragment.lower() in v.reason.lower()


def test_a_second_statement_is_refused():
    v = validate_cypher("MATCH (s:Supplier) RETURN s.lifnr; MATCH (m:Material) RETURN m")
    assert not v.ok and "multiple statements" in v.reason


def test_a_query_that_reads_nothing_is_refused():
    v = validate_cypher("RETURN 1 AS answer LIMIT 1")
    assert not v.ok and "MATCH" in v.reason


def test_an_invented_label_is_refused():
    v = validate_cypher("MATCH (w:Warehouse)-[:STOCKED_AT]->(p:Plant) RETURN w LIMIT 5")
    assert not v.ok
    assert "Warehouse" in v.reason
    assert "Supplier" in v.reason, "the reason should name what is actually available"


def test_an_invented_relationship_type_is_refused():
    v = validate_cypher(
        "MATCH (s:Supplier)-[:SHIPS_LATE]->(m:Material) RETURN s.lifnr LIMIT 5"
    )
    assert not v.ok and "SHIPS_LATE" in v.reason


def test_a_missing_limit_is_injected_rather_than_refused():
    v = validate_cypher("MATCH (s:Supplier) RETURN s.lifnr AS lifnr")
    assert v.ok and v.limit_injected
    assert v.query.endswith(f"LIMIT {CYPHER_ROW_LIMIT}")


def test_keywords_inside_literals_are_not_write_clauses():
    """'Fastener Set M8' is a material description, not a SET clause."""
    v = validate_cypher(
        "MATCH (m:Material) WHERE m.name = 'Fastener Set M8 Aerospace' "
        "RETURN m.matnr AS matnr LIMIT 5"
    )
    assert v.ok, v.reason


def test_property_keys_are_not_mistaken_for_labels():
    v = validate_cypher(
        "MATCH (s:Supplier {lifnr: '0000001000'})-[:SUPPLIES]->(m:Material) "
        "RETURN m.matnr AS matnr LIMIT 5"
    )
    assert v.ok, v.reason
    assert v.labels == ["Supplier", "Material"]


def test_translation_degrades_cleanly_with_no_llm():
    """No key configured: no query, an explanation, and nothing invented."""
    t = translate_to_cypher("Which customers depend on Apex Microelectronics?")
    assert isinstance(t, CypherTranslation)
    assert t.valid is False
    assert t.query is None
    assert t.rows == [] and t.executed is False
    assert "No LLM is configured" in t.reason


def test_the_in_process_backend_returns_the_query_instead_of_fake_rows(backend):
    t = CypherTranslation(question="q", query=READ_QUERY, valid=True)
    execute_cypher(backend, t)
    assert t.executed is False
    assert t.rows == []
    assert t.query == READ_QUERY, "the validated query still has to come back"
    assert "GRAPH_BACKEND=neo4j" in t.execution_note


def test_endpoint_answers_with_a_verdict_not_an_error(client):
    r = client.post("/api/query/cypher", json={"question": "Who supplies MCU-32?"})
    assert r.status_code == 200
    d = r.json()
    assert d["valid"] is False
    assert d["executed"] is False
    assert d["rows"] == []
    assert d["reason"]
