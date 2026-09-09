"""Bills of material: integrity, the reverse read, and the multi-level cascade.

A BOM that does not tie back to MARA, or reservations that have drifted away
from the BOM they were exploded from, would let the traversal walk edges that
do not exist in the source system. So the structure is checked before the
cascade that rides on it.
"""

import json
from datetime import date, timedelta

import pytest

from app.config import DATA_DIR
from app.engines.avoidance import find_actions
from app.engines.deterministic import run_traversal
from app.engines.financial import compute_exposure
from tests.conftest import DELAY, TOSHIRO


def load(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


@pytest.fixture(scope="module")
def bom():
    return {n: load(n) for n in ("bom_link", "bom_header", "bom_item",
                                "materials", "plants", "prod_order_header",
                                "reservations")}


# --------------------------------------------------------------------------
# Referential integrity
# --------------------------------------------------------------------------
def test_bom_tables_join_cleanly(bom):
    materials = {m["MATNR"] for m in bom["materials"]}
    plants = {p["WERKS"] for p in bom["plants"]}
    headers = {(h["STLNR"], h["STLAL"]) for h in bom["bom_header"]}
    links = {(link["STLNR"], link["STLAL"]) for link in bom["bom_link"]}

    for link in bom["bom_link"]:
        assert link["MATNR"] in materials, f"MAST.MATNR {link['MATNR']} not in MARA"
        assert link["WERKS"] in plants, f"MAST.WERKS {link['WERKS']} not in T001W"
        assert (link["STLNR"], link["STLAL"]) in headers, "MAST without an STKO header"

    for h in bom["bom_header"]:
        assert float(h["BMENG"]) > 0, "STKO.BMENG must be positive: it is a divisor"

    for item in bom["bom_item"]:
        assert item["IDNRK"] in materials, f"STPO.IDNRK {item['IDNRK']} not in MARA"
        assert (item["STLNR"], item["STLAL"]) in links, "STPO without a MAST link"
        assert float(item["MENGE"]) > 0

    with_items = {(i["STLNR"], i["STLAL"]) for i in bom["bom_item"]}
    assert links == with_items, "a BOM header with no components is not a BOM"


def test_bom_is_acyclic_and_correctly_levelled(bom):
    """A material may not contain itself, directly or through its children, and
    only produced materials own a BOM."""
    mtart = {m["MATNR"]: m["MTART"] for m in bom["materials"]}
    stlnr_to_parent = {(link["STLNR"], link["STLAL"]): link["MATNR"]
                       for link in bom["bom_link"]}
    children = {}
    for item in bom["bom_item"]:
        parent = stlnr_to_parent[(item["STLNR"], item["STLAL"])]
        children.setdefault(parent, []).append(item["IDNRK"])

    for parent in children:
        assert mtart[parent] in ("HALB", "FERT"), (
            f"{parent} is {mtart[parent]}: a purchased part cannot own a BOM"
        )

    for parent, comps in children.items():
        seen, stack = set(), list(comps)
        while stack:
            comp = stack.pop()
            assert comp != parent, f"{parent} contains itself"
            if comp in seen:
                continue
            seen.add(comp)
            stack.extend(children.get(comp, []))


def test_every_sub_assembly_is_consumed_by_something(bom):
    """A HALB that no assembly consumes is a dead end in the graph -- exactly
    the gap the BOM model exists to close."""
    consumed = {i["IDNRK"] for i in bom["bom_item"]}
    halb = [m["MATNR"] for m in bom["materials"] if m["MTART"] == "HALB"]
    assert halb, "fixture should carry semi-finished materials"
    for matnr in halb:
        assert matnr in consumed, f"{matnr} is produced but goes into nothing"


def test_reservations_are_the_bom_exploded_by_order_quantity(bom):
    """RESB is derived, not hand-written: SAP explodes it from the BOM when the
    order is created, and BDMNG = GAMNG / STKO.BMENG x STPO.MENGE."""
    orders = {a["AUFNR"]: a for a in bom["prod_order_header"]}
    base = {(h["STLNR"], h["STLAL"]): float(h["BMENG"]) for h in bom["bom_header"]}
    by_parent = {}
    for link in bom["bom_link"]:
        key = (link["STLNR"], link["STLAL"])
        for item in bom["bom_item"]:
            if (item["STLNR"], item["STLAL"]) == key:
                by_parent.setdefault(link["MATNR"], {})[item["IDNRK"]] = (
                    float(item["MENGE"]) / base[key]
                )

    reserved = {}
    for r in bom["reservations"]:
        reserved.setdefault(r["AUFNR"], {})[r["MATNR"]] = float(r["BDMNG"])

    for aufnr, order in orders.items():
        components = by_parent[order["PLNBEZ"]]
        assert set(reserved[aufnr]) == set(components), (
            f"order {aufnr} reserves {sorted(reserved[aufnr])} but the "
            f"{order['PLNBEZ']} BOM lists {sorted(components)}"
        )
        for matnr, per_unit in components.items():
            expected = float(order["GAMNG"]) * per_unit
            assert reserved[aufnr][matnr] == pytest.approx(expected), (
                f"{aufnr}/{matnr}: RESB.BDMNG has drifted from the BOM"
            )


# --------------------------------------------------------------------------
# The semantic query surface
# --------------------------------------------------------------------------
def test_where_used_names_the_assemblies_that_consume_a_material(backend):
    assert {r["MATNR"] for r in backend.where_used("FCB-100")} == {"FMS-850"}
    assert {r["MATNR"] for r in backend.where_used("SENSOR-ARR-4")} == {
        "ACU-500", "CSM-300", "FMS-850"
    }
    assert {r["MATNR"] for r in backend.where_used("PSU-220")} == {"APU-600"}
    # A purchased part is consumed but never assembled into by anything below it.
    assert backend.bom_for_material("MCU-32") == []
    assert {r["MATNR"] for r in backend.where_used("MCU-32")} == {
        "ACU-500", "CSM-300", "FCB-100"
    }


def test_where_used_is_the_exact_inverse_of_bom_for_material(backend):
    """The two reads must describe one relation, or the traversal can walk up an
    edge that does not exist on the way down."""
    materials = [m["MATNR"] for m in backend.t["materials"]]
    downward = {
        (parent, c["IDNRK"], c["MENGE"], c["BMENG"])
        for parent in materials
        for c in backend.bom_for_material(parent)
    }
    upward = {
        (r["MATNR"], component, r["MENGE"], r["BMENG"])
        for component in materials
        for r in backend.where_used(component)
    }
    assert downward == upward
    assert downward, "fixture should carry bills of material"


def test_bom_quantities_are_stated_against_the_base_quantity(backend):
    """STPO.MENGE alone is meaningless without STKO.BMENG: 100 MCU-32 per BOM is
    16.67 per unit when the base quantity is 6."""
    acu = {c["IDNRK"]: c for c in backend.bom_for_material("ACU-500")}
    assert acu["MCU-32"]["MENGE"] == 100.0
    assert acu["MCU-32"]["BMENG"] == 6.0
    assert acu["MCU-32"]["qty_per_unit"] == pytest.approx(100 / 6)


def test_bom_reaches_the_graph_snapshot(backend):
    nodes, edges = backend.graph_snapshot()
    bom_nodes = [n for n in nodes if n["label"] == "BOMItem"]
    assert bom_nodes
    for n in bom_nodes:
        assert {"stlnr", "idnrk", "menge"} <= set(n["properties"])
    kinds = {e["type"] for e in edges}
    assert {"COMPONENT_OF", "ASSEMBLES_INTO"} <= kinds


# --------------------------------------------------------------------------
# Multi-level explosion
# --------------------------------------------------------------------------
def test_cascade_reaches_a_finished_good_through_a_sub_assembly(traversal):
    """Order 9002 builds FCB-100 and is halted by the MCU-32/PWR-IC-7 shortfall.
    FMS-850 consumes FCB-100, so order 9008 must be halted too -- it reserves
    none of Apex's materials, and RESB alone would never have reached it."""
    fms = next((p for p in traversal.production_orders if p.aufnr == "000009008"), None)
    assert fms is not None, "the BOM cascade did not reach FMS-850"
    assert fms.output_matnr == "FMS-850"
    assert fms.blocking_subassemblies == ["FCB-100"]
    assert fms.blocking_materials == ["MCU-32", "PWR-IC-7"], (
        "the parent should inherit the materials a buyer can act on"
    )


def test_cascaded_halt_derives_from_the_feeding_order_not_a_constant(backend, traversal):
    """9002 finishes 12 days late; 9008 needs FCB-100 on a date 5 days after
    9002's original finish, so it loses 7 of those days, not all 12."""
    child = next(p for p in traversal.production_orders if p.aufnr == "000009002")
    parent = next(p for p in traversal.production_orders if p.aufnr == "000009008")
    need = next(r for r in backend.reservations_of_order("000009008")
                if r["MATNR"] == "FCB-100")
    expected = (child.projected_finish - _date(need["BDTER"])).days
    assert parent.halt_days == float(expected) == 7.0
    assert parent.projected_finish == parent.scheduled_finish + timedelta(days=expected)


def test_cascaded_order_carries_bom_lineage(traversal):
    parent = next(p for p in traversal.production_orders if p.aufnr == "000009008")
    tables = {s.sap_table for s in parent.lineage.steps}
    assert "STPO" in tables, "the BOM step must be citable, not implied"
    assert {"RESB", "AFKO"} <= tables
    assert "FCB-100" in parent.lineage.derivation
    assert "STPO.IDNRK" in parent.lineage.derivation


def test_sub_assembly_covered_by_stock_does_not_cascade(backend, traversal):
    """SENSOR-ARR-4 goes into three finished goods, but order 9009 that builds
    it is not halted, so nothing propagates from it. The cascade follows the
    data, not the shape of the BOM."""
    assert backend.where_used("SENSOR-ARR-4"), "fixture precondition"
    assert not any(p.aufnr == "000009009" for p in traversal.production_orders)
    for p in traversal.production_orders:
        assert "SENSOR-ARR-4" not in p.blocking_subassemblies


def test_cascade_adds_revenue_it_can_prove(traversal, exposure):
    """FMS-850's sales order is exposed only because the BOM connects it to the
    shortfall; the figure has to be the sales order's own net value."""
    fms_sales = [s for s in traversal.sales_orders if s.matnr == "FMS-850"]
    assert fms_sales, "the cascade should have reached FMS-850's demand"
    assert sum(s.net_value for s in fms_sales) == 14_600_000.0
    assert exposure.revenue_at_risk == 99_500_000.0


def test_contrast_supplier_still_cascades_nowhere(backend):
    """The BOM must not become a way to manufacture exposure: with no shortfall
    there is no halted order to explode from."""
    t = run_traversal(backend, TOSHIRO, DELAY)
    e = compute_exposure(t, backend)
    assert t.production_orders == []
    assert e.total_financial_exposure == 0.0


def test_plan_will_not_defer_an_order_that_feeds_a_committed_assembly(backend, plan):
    """Order 9002 has no sales order of its own, which used to make it look free
    to defer. The BOM shows it builds the FCB-100 that FMS-850 needs, and a
    customer is waiting on FMS-850."""
    deferred = {a.title.split()[3] for a in plan.actions
                if a.kind == "production_resequence"}
    assert "000009002" not in deferred
    assert {r["MATNR"] for r in backend.where_used("FCB-100")} == {"FMS-850"}


def test_plan_still_defers_an_order_nothing_depends_on(backend, traversal, plan):
    """The guard must not become blanket caution: PSU-220 rolls up only into
    APU-600, which no halted order builds, so deferring 9005 is still free."""
    deferred = {a.title.split()[3] for a in plan.actions
                if a.kind == "production_resequence"}
    assert "000009005" in deferred
    committed = {so.matnr for so in traversal.sales_orders}
    assert not {r["MATNR"] for r in backend.where_used("PSU-220")} & committed


def test_avoidance_plan_remains_worth_taking(plan):
    assert plan.mitigation_pct > 0.80
    assert plan.total_avoidance_cost < plan.total_risk_mitigated
