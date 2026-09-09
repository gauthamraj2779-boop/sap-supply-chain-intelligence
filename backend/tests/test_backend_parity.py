"""The two graph backends must not diverge.

The whole design rests on Neo4j and the in-process store being interchangeable:
engines call semantic methods, never query strings, and the deterministic
figures are supposed to be a property of the data rather than of the storage.

That guarantee was silently false. neo4j's Record.data() renders a relationship
as the tuple (start_props, type, end_props), not a property map, so three
methods that returned relationship variables raised TypeError. The traversal
swallowed it as a failed hop and reported 0 exposure against 111,174,000 from
the same data. Nothing failed loudly; the number was just wrong.

These tests skip when Neo4j is not configured, so the suite stays hermetic.
"""

import os

import pytest

from app.config import Settings
from app.engines.orchestrator import analyse
from app.graph.backends.memory import MemoryBackend

APEX = "0000001000"
TOSHIRO = "0000001002"


def _rows(rows):
    """Order-insensitive comparison of a list of records.

    str(dict) reflects key insertion order, which legitimately differs between
    the two implementations; comparing reprs would fail on identical rows.
    """
    return sorted((sorted(r.items(), key=repr) for r in rows), key=repr)


def _neo4j_backend():
    settings = Settings()
    if not settings.neo4j_configured:
        pytest.skip("Neo4j is not configured; parity is unverifiable here")
    from app.graph.backends.neo4j_backend import Neo4jBackend

    backend = Neo4jBackend(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
    )
    try:
        backend.connect()
    except Exception as exc:
        pytest.skip(f"Neo4j unreachable: {exc}")
    if not backend.counts():
        backend.close()
        pytest.skip("Neo4j is empty; run `make load` first")
    return backend


@pytest.fixture(scope="module")
def neo():
    backend = _neo4j_backend()
    yield backend
    backend.close()


@pytest.fixture(scope="module")
def mem():
    backend = MemoryBackend()
    backend.connect()
    yield backend
    backend.close()


def test_every_semantic_method_agrees(neo, mem):
    """Each accessor, not just the headline. A relationship-returning method
    can be broken while node-returning ones look fine."""
    assert neo.supplier(APEX) == mem.supplier(APEX)
    assert neo.material("MCU-32") == mem.material("MCU-32")
    assert neo.plant("1010") == mem.plant("1010")
    assert neo.customer("0000002001") == mem.customer("0000002001")

    # Relationship-backed: these are the ones that were silently returning
    # tuples instead of property maps.
    assert neo.stock("MCU-32", "1010") == mem.stock("MCU-32", "1010")
    assert _rows(neo.stock_all_plants("MCU-32")) == _rows(mem.stock_all_plants("MCU-32"))
    assert _rows(neo.alternate_sources("MCU-32", APEX)) == _rows(
        mem.alternate_sources("MCU-32", APEX)
    )

    # Compare dicts, not their repr: str(dict) reflects key insertion order,
    # which legitimately differs between the two implementations and would fail
    # on rows that are in fact identical.
    def key(rows):
        return sorted((sorted(r.items(), key=repr) for r in rows), key=repr)
    assert key(neo.open_schedule_lines_for_supplier(APEX)) == key(
        mem.open_schedule_lines_for_supplier(APEX)
    )
    assert key(neo.reservations_for("MCU-32", "1010")) == key(
        mem.reservations_for("MCU-32", "1010")
    )
    assert key(neo.sales_items_for_material("ACU-500")) == key(
        mem.sales_items_for_material("ACU-500")
    )
    assert key(neo.bom_for_material("ACU-500")) == key(mem.bom_for_material("ACU-500"))
    assert key(neo.where_used("MCU-32")) == key(mem.where_used("MCU-32"))


def test_no_method_returns_a_relationship_tuple(neo):
    """The failure mode itself, asserted directly.

    A tuple here means a relationship variable was returned without
    properties(), which reads as a silent data loss rather than an error.
    """
    for value in (
        neo.stock("MCU-32", "1010"),
        *neo.stock_all_plants("MCU-32"),
        *neo.alternate_sources("MCU-32", APEX),
    ):
        assert isinstance(value, dict), f"expected a property map, got {type(value)}"


@pytest.mark.parametrize("supplier,delay", [(APEX, 14), (APEX, 30), (TOSHIRO, 14)])
def test_reports_are_identical(neo, mem, supplier, delay):
    a = analyse(neo, supplier, delay, include_narrative=False)
    b = analyse(mem, supplier, delay, include_narrative=False)

    assert (
        a.financial_exposure.total_financial_exposure
        == b.financial_exposure.total_financial_exposure
    )
    assert a.financial_exposure.model_dump() == b.financial_exposure.model_dump()
    assert a.affected_counts == b.affected_counts
    assert a.traversal.hops_failed == b.traversal.hops_failed == []
    assert [x.aufnr for x in a.traversal.production_orders] == [
        x.aufnr for x in b.traversal.production_orders
    ]


def test_only_neo4j_offers_raw_cypher(neo, mem):
    from app.graph.adapter import GraphUnavailable

    assert neo.supports_cypher
    assert neo.run_cypher("MATCH (s:Supplier) RETURN count(s) AS n")[0]["n"] > 0
    with pytest.raises(GraphUnavailable):
        neo.run_cypher("MATCH (s:Supplier) DELETE s")

    assert not mem.supports_cypher
    with pytest.raises(GraphUnavailable):
        mem.run_cypher("MATCH (n) RETURN n")
