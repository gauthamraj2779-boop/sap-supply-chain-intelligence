"""Referential integrity of the generated SAP dataset.

A graph built on dangling keys produces confident nonsense, so every foreign
key is checked before anything else is trusted.
"""

import json

from app.config import DATA_DIR

import pytest


def load(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def tables():
    names = ("plants", "suppliers", "customers", "materials", "material_plant",
             "material_stock", "source_list", "po_header", "po_item", "po_schedule",
             "prod_order_header", "prod_order_item", "reservations",
             "so_header", "so_item", "delivery_header", "delivery_item")
    return {n: load(n) for n in names}


def test_all_tables_present_and_non_empty(tables):
    for name, rows in tables.items():
        assert rows, f"{name}.json is empty"


def test_foreign_keys_resolve(tables):
    materials = {m["MATNR"] for m in tables["materials"]}
    plants = {p["WERKS"] for p in tables["plants"]}
    suppliers = {s["LIFNR"] for s in tables["suppliers"]}
    customers = {c["KUNNR"] for c in tables["customers"]}
    po_keys = {(i["EBELN"], i["EBELP"]) for i in tables["po_item"]}
    orders = {a["AUFNR"] for a in tables["prod_order_header"]}
    so_keys = {(i["VBELN"], i["POSNR"]) for i in tables["so_item"]}
    deliveries = {d["VBELN"] for d in tables["delivery_header"]}

    for r in tables["po_header"]:
        assert r["LIFNR"] in suppliers, f"EKKO.LIFNR {r['LIFNR']} not in LFA1"
    for r in tables["po_item"]:
        assert r["MATNR"] in materials, f"EKPO.MATNR {r['MATNR']} not in MARA"
        assert r["WERKS"] in plants, f"EKPO.WERKS {r['WERKS']} not in T001W"
    for r in tables["po_schedule"]:
        assert (r["EBELN"], r["EBELP"]) in po_keys, "EKET without an EKPO line"
    for r in tables["material_plant"] + tables["material_stock"]:
        assert r["MATNR"] in materials and r["WERKS"] in plants
    for r in tables["source_list"]:
        assert r["MATNR"] in materials and r["LIFNR"] in suppliers
    for r in tables["prod_order_header"]:
        assert r["PLNBEZ"] in materials and r["WERKS"] in plants
    for r in tables["reservations"]:
        assert r["AUFNR"] in orders, f"RESB.AUFNR {r['AUFNR']} not in AFKO"
        assert r["MATNR"] in materials and r["WERKS"] in plants
    for r in tables["so_header"]:
        assert r["KUNNR"] in customers
    for r in tables["so_item"]:
        assert r["MATNR"] in materials and r["WERKS"] in plants
    for r in tables["delivery_header"]:
        assert r["KUNNR"] in customers
    for r in tables["delivery_item"]:
        assert r["VBELN"] in deliveries, "LIPS without a LIKP header"
        assert (r["VGBEL"], r["VGPOS"]) in so_keys, "LIPS.VGBEL without a VBAP line"


def test_sap_field_names_are_authentic(tables):
    """Judges will check these against real SAP. They must be right."""
    assert set(tables["suppliers"][0]) >= {"LIFNR", "NAME1", "LAND1"}
    assert set(tables["materials"][0]) >= {"MATNR", "MAKTX", "MTART", "MEINS"}
    assert set(tables["po_item"][0]) >= {"EBELN", "EBELP", "MATNR", "MENGE", "NETWR"}
    assert set(tables["po_schedule"][0]) >= {"EBELN", "EBELP", "ETENR", "EINDT"}
    assert set(tables["reservations"][0]) >= {"RSNUM", "RSPOS", "AUFNR", "BDMNG", "BDTER"}
    assert set(tables["prod_order_header"][0]) >= {"AUFNR", "PLNBEZ", "GAMNG", "GLTRP"}
    assert set(tables["so_item"][0]) >= {"VBELN", "POSNR", "KWMENG", "NETWR"}
    assert set(tables["delivery_header"][0]) >= {"VBELN", "KUNNR", "LFDAT"}
    assert set(tables["material_stock"][0]) >= {"MATNR", "WERKS", "LGORT", "LABST"}


def test_planted_scenario_is_intact(tables):
    """The demo depends on these conditions; assert them rather than hope."""
    src = tables["source_list"]
    mcu_sources = {r["LIFNR"] for r in src if r["MATNR"] == "MCU-32"}
    assert "0000001000" in mcu_sources, "Apex must source MCU-32"
    assert "0000001001" in mcu_sources, "Nova must be an alternate for MCU-32"

    pwr_sources = {r["LIFNR"] for r in src if r["MATNR"] == "PWR-IC-7"}
    assert pwr_sources == {"0000001000"}, "PWR-IC-7 must be single-sourced from Apex"

    stock = {(r["MATNR"], r["WERKS"]): r["LABST"] for r in tables["material_stock"]}
    assert stock[("MCU-32", "1010")] == 850.0, "thin stock at the affected plant"
    assert stock[("MCU-32", "1020")] == 800.0, "transferable stock at another plant"


def test_non_sap_assumptions_are_labelled(tables):
    """Every figure that is not an SAP field must say so in the data itself."""
    for p in tables["plants"]:
        assert "idle_plant_cost_per_day" in p
        assert "_assumption" in p, "idle plant cost must be declared an assumption"
    for d in tables["delivery_header"]:
        assert "penalty_rate" in d and "_assumption" in d
