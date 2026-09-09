"""DDIC-style data dictionary catalog for the generated dataset.

Mirrors what SAP's own DD02T/DD03L would return for these tables: one row per
field with its position, key flag, data element, domain, short text and
**check table**. Check tables are SAP's declared foreign keys and are the single
strongest signal the discovery stage has.

Deliberate gaps
---------------
Three genuine relationships carry NO check table here. That is not an oversight
and it is not artificial: each one matches how real SAP behaves.

  * ``LIPS.VGBEL -> VBAK.VBELN`` - the reference-document field is generic. It
    can hold a sales order, a contract or a purchase order, so DDIC cannot
    declare one check table for it.
  * ``RESB.AUFNR -> AFKO.AUFNR``  - a reservation's order reference can point at
    a production order, a project or a maintenance order.
  * ``LIKP.VSTEL -> T001W.WERKS`` - the shipping point checks against TVST, a
    table outside this catalog; the values in this dataset are plant codes.

A lookup cannot find those. Only the data can: the profiler still measures ~1.0
containment for all three, so the discovery stage has to infer them from
overlap. They come back with ``inferred: true`` and a lower, grounded
confidence, which is the whole point of the exercise.

Run:  python -m data.synthetic.ddic_catalog
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = OUT_DIR / "ddic_catalog.json"

# Non-SAP columns are catalogued too, with no data element and no domain, so a
# reader can see at a glance which figures are ERP master data and which are
# management-accounting or contractual inputs the project added.
_ASSUMPTION = "Non-SAP: management accounting / contract input, not a DDIC field"

TABLE_DESCRIPTIONS: dict[str, str] = {
    "T001W": "Plants/Branches",
    "LFA1": "Vendor Master (General Section)",
    "KNA1": "General Data in Customer Master",
    "MARA": "General Material Data",
    "MARC": "Plant Data for Material",
    "MARD": "Storage Location Data for Material",
    "EINA": "Purchasing Info Record: General Data (joined with EINE org data)",
    "EKKO": "Purchasing Document Header",
    "EKPO": "Purchasing Document Item",
    "EKET": "Scheduling Agreement Schedule Lines",
    "AFKO": "Order Header Data PP Orders",
    "AFPO": "Order Item",
    "RESB": "Reservation/Dependent Requirements",
    "VBAK": "Sales Document: Header Data",
    "VBAP": "Sales Document: Item Data",
    "LIKP": "SD Document: Delivery Header Data",
    "LIPS": "SD Document: Delivery: Item Data",
}

# table -> [(field, key_flag, data_element, domain, short text, check_table)]
# Check tables that are real in SAP but outside this catalog (T005, T006, T161,
# TCURC ...) are kept: discovery must cope with references it cannot resolve,
# exactly as it would against a real system where only a slice is in scope.
FIELDS: dict[str, list[tuple[str, bool, str | None, str | None, str, str | None]]] = {
    "T001W": [
        ("WERKS", True, "WERKS_D", "WERKS", "Plant", None),
        ("NAME1", False, "NAME1", "TEXT30", "Name", None),
        ("LAND1", False, "LAND1", "LAND1", "Country Key", "T005"),
        ("ORT01", False, "ORT01", "TEXT25", "City", None),
        ("idle_plant_cost_per_day", False, None, None, _ASSUMPTION, None),
    ],
    "LFA1": [
        ("LIFNR", True, "LIFNR", "LIFNR", "Account Number of Vendor or Creditor", None),
        ("NAME1", False, "NAME1_GP", "TEXT35", "Name 1", None),
        ("LAND1", False, "LAND1_GP", "LAND1", "Country Key", "T005"),
        ("ORT01", False, "ORT01_GP", "TEXT35", "City", None),
        ("risk_score", False, None, None, _ASSUMPTION, None),
    ],
    "KNA1": [
        ("KUNNR", True, "KUNNR", "KUNNR", "Customer Number", None),
        ("NAME1", False, "NAME1_GP", "TEXT35", "Name 1", None),
        ("LAND1", False, "LAND1_GP", "LAND1", "Country Key", "T005"),
        ("ORT01", False, "ORT01_GP", "TEXT35", "City", None),
    ],
    "MARA": [
        ("MATNR", True, "MATNR", "MATNR", "Material Number", None),
        ("MAKTX", False, "MAKTX", "TEXT40", "Material Description (Short Text)", None),
        ("MTART", False, "MTART", "MTART", "Material Type", "T134"),
        ("MATKL", False, "MATKL", "MATKL", "Material Group", "T023"),
        ("MEINS", False, "MEINS", "MEINS", "Base Unit of Measure", "T006"),
        ("unit_cost", False, None, None, _ASSUMPTION, None),
    ],
    "MARC": [
        ("MATNR", True, "MATNR", "MATNR", "Material Number", "MARA"),
        ("WERKS", True, "WERKS_D", "WERKS", "Plant", "T001W"),
        ("DISPO", False, "DISPO", "DISPO", "MRP Controller", "T024D"),
        ("PLIFZ", False, "PLIFZ", "DEC3", "Planned Delivery Time in Days", None),
        ("EISBE", False, "EISBE", "MENG13V", "Safety Stock", None),
        ("BESKZ", False, "BESKZ", "BESKZ", "Procurement Type", None),
    ],
    "MARD": [
        ("MATNR", True, "MATNR", "MATNR", "Material Number", "MARA"),
        ("WERKS", True, "WERKS_D", "WERKS", "Plant", "T001W"),
        ("LGORT", True, "LGORT_D", "LGORT", "Storage Location", "T001L"),
        ("LABST", False, "LABST", "MENG13V", "Valuated Unrestricted-Use Stock", None),
    ],
    "EINA": [
        ("MATNR", True, "MATNR", "MATNR", "Material Number", "MARA"),
        ("LIFNR", True, "LIFNR", "LIFNR", "Vendor Account Number", "LFA1"),
        ("NETPR", False, "NETPR", "WERT7", "Net Price in Purchasing Info Record", None),
        ("APLFZ", False, "APLFZ", "DEC3", "Planned Delivery Time in Days", None),
        ("is_primary", False, None, None, _ASSUMPTION, None),
        ("unit_cost", False, None, None, _ASSUMPTION, None),
    ],
    "EKKO": [
        ("EBELN", True, "EBELN", "EBELN", "Purchasing Document Number", None),
        ("LIFNR", False, "ELIFN", "LIFNR", "Vendor Account Number", "LFA1"),
        ("BUKRS", False, "BUKRS", "BUKRS", "Company Code", "T001"),
        ("BEDAT", False, "EBDAT", "DATUM", "Purchasing Document Date", None),
        ("BSART", False, "ESART", "BSART", "Purchasing Document Type", "T161"),
        ("WAERS", False, "WAERS", "WAERS", "Currency Key", "TCURC"),
    ],
    "EKPO": [
        ("EBELN", True, "EBELN", "EBELN", "Purchasing Document Number", "EKKO"),
        ("EBELP", True, "EBELP", "EBELP", "Item Number of Purchasing Document", None),
        ("MATNR", False, "MATNR", "MATNR", "Material Number", "MARA"),
        ("TXZ01", False, "TXZ01", "TEXT40", "Short Text", None),
        ("WERKS", False, "EWERK", "WERKS", "Plant", "T001W"),
        ("MENGE", False, "BSTMG", "MENG13", "Purchase Order Quantity", None),
        ("MEINS", False, "BSTME", "MEINS", "Order Unit", "T006"),
        ("NETPR", False, "BPREI", "WERT7", "Net Price in Purchasing Document", None),
        ("NETWR", False, "BWERT", "WERT7", "Net Order Value in PO Currency", None),
        ("ELIKZ", False, "ELIKZ", "XFELD", "Delivery Completed Indicator", None),
    ],
    "EKET": [
        ("EBELN", True, "EBELN", "EBELN", "Purchasing Document Number", "EKKO"),
        ("EBELP", True, "EBELP", "EBELP", "Item Number of Purchasing Document", "EKPO"),
        ("ETENR", True, "ETENR", "ETENR", "Delivery Schedule Line Counter", None),
        ("EINDT", False, "EINDT", "DATUM", "Item Delivery Date", None),
        ("MENGE", False, "ETMEN", "MENG13", "Scheduled Quantity", None),
        ("WEMNG", False, "WEMNG", "MENG13", "Quantity of Goods Received", None),
    ],
    "AFKO": [
        # AUFNR carries no check table: AFKO is the order header of record for
        # this catalog, and SAP's own AUFK reference is outside its scope.
        ("AUFNR", True, "AUFNR", "AUFNR", "Order Number", None),
        ("PLNBEZ", False, "PLNBEZ", "MATNR", "Material Number for BOM Explosion", "MARA"),
        ("GAMNG", False, "GAMNG", "MENG13", "Total Order Quantity", None),
        ("GSTRP", False, "GSTRP", "DATUM", "Basic Start Date", None),
        ("GLTRP", False, "GLTRP", "DATUM", "Basic Finish Date", None),
        ("WERKS", False, "WERKS_D", "WERKS", "Plant", "T001W"),
    ],
    "AFPO": [
        ("AUFNR", True, "AUFNR", "AUFNR", "Order Number", "AFKO"),
        ("POSNR", True, "CO_POSNR", "NUM04", "Order Item Number", None),
        ("MATNR", False, "MATNR", "MATNR", "Material Number", "MARA"),
        ("PSMNG", False, "PSMNG", "MENG13", "Order Item Quantity", None),
        ("WERKS", False, "PWERK", "WERKS", "Plant", "T001W"),
    ],
    "RESB": [
        ("RSNUM", True, "RSNUM", "RSNUM", "Number of Reservation/Dependent Requirement", None),
        ("RSPOS", True, "RSPOS", "RSPOS", "Item Number of Reservation", None),
        # No check table: the order reference is generic in SAP (production
        # order, project or maintenance order), so DDIC cannot declare one.
        ("AUFNR", False, "AUFNR", "AUFNR", "Order Number", None),
        ("MATNR", False, "MATNR", "MATNR", "Material Number", "MARA"),
        ("WERKS", False, "WERKS_D", "WERKS", "Plant", "T001W"),
        ("BDMNG", False, "BDMNG", "MENG13", "Requirement Quantity", None),
        ("BDTER", False, "BDTER", "DATUM", "Requirement Date", None),
        ("ENMNG", False, "ENMNG", "MENG13", "Quantity Withdrawn", None),
    ],
    "VBAK": [
        ("VBELN", True, "VBELN_VA", "VBELN", "Sales Document", None),
        ("KUNNR", False, "KUNAG", "KUNNR", "Sold-to Party", "KNA1"),
        ("AUDAT", False, "AUDAT", "DATUM", "Document Date", None),
        ("NETWR", False, "NETWR_AK", "WERTV8", "Net Value of the Sales Order", None),
        ("WAERK", False, "WAERK", "WAERS", "SD Document Currency", "TCURC"),
        ("VKORG", False, "VKORG", "VKORG", "Sales Organization", "TVKO"),
    ],
    "VBAP": [
        ("VBELN", True, "VBELN_VA", "VBELN", "Sales Document", "VBAK"),
        ("POSNR", True, "POSNR_VA", "POSNR", "Sales Document Item", None),
        ("MATNR", False, "MATNR", "MATNR", "Material Number", "MARA"),
        ("ARKTX", False, "ARKTX", "TEXT40", "Short Text for Sales Order Item", None),
        ("WERKS", False, "WERKS_EXT", "WERKS", "Plant", "T001W"),
        ("KWMENG", False, "KWMENG", "MENG15", "Cumulative Order Quantity in Sales Units", None),
        ("NETWR", False, "NETWR_AP", "WERTV8", "Net Value of the Order Item", None),
    ],
    "LIKP": [
        ("VBELN", True, "VBELN_VL", "VBELN", "Delivery", None),
        ("KUNNR", False, "KUNWE", "KUNNR", "Ship-to Party", "KNA1"),
        ("LFDAT", False, "LFDAT_V", "DATUM", "Delivery Date", None),
        ("WADAT", False, "WADAT", "DATUM", "Planned Goods Movement Date", None),
        # No check table into this catalog: VSTEL checks against TVST (shipping
        # points), and the values here happen to be plant codes.
        ("VSTEL", False, "VSTEL", "VSTEL", "Shipping Point/Receiving Point", None),
        ("LFART", False, "LFART", "LFART", "Delivery Type", "TVLK"),
        ("penalty_rate", False, None, None, _ASSUMPTION, None),
    ],
    "LIPS": [
        ("VBELN", True, "VBELN_VL", "VBELN", "Delivery", "LIKP"),
        ("POSNR", True, "POSNR_VL", "POSNR", "Delivery Item", None),
        ("MATNR", False, "MATNR", "MATNR", "Material Number", "MARA"),
        ("WERKS", False, "WERKS_D", "WERKS", "Plant", "T001W"),
        ("LFIMG", False, "LFIMG", "MENG13", "Actual Quantity Delivered (in Sales Units)", None),
        # No check table: the reference document field is generic in SAP and can
        # hold a sales order, a contract or a purchase order.
        ("VGBEL", False, "VGBEL", "VBELN", "Document Number of the Reference Document", None),
        ("VGPOS", False, "VGPOS", "POSNR", "Item Number of the Reference Item", None),
        ("NETWR", False, "NETWR_FP", "WERTV8", "Net Value in Document Currency", None),
    ],
}

# Verification ground truth, NOT an input to discovery. The pipeline never
# imports this; only the test suite does, to prove the three relationships above
# were reconstructed from data overlap rather than read out of the catalog.
WITHHELD_CHECK_TABLES: tuple[tuple[str, str, str, str], ...] = (
    ("LIPS", "VGBEL", "VBAK", "VBELN"),
    ("RESB", "AUFNR", "AFKO", "AUFNR"),
    ("LIKP", "VSTEL", "T001W", "WERKS"),
)


def build() -> list[dict]:
    """One row per field, in table then position order."""
    rows: list[dict] = []
    for table, fields in FIELDS.items():
        desc = TABLE_DESCRIPTIONS[table]
        for position, (name, key, elem, domain, text, check) in enumerate(fields, start=1):
            rows.append({
                "table": table,
                "table_desc": desc,
                "field": name,
                "position": position,
                "key_flag": key,
                "data_element": elem,
                "domain": domain,
                "field_desc": text,
                "check_table": check,
            })
    return rows


def load(path: Path = CATALOG_PATH) -> list[dict]:
    """The catalog from disk, rebuilt in memory if it has not been emitted."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return build()


def key_fields(rows: list[dict] | None = None) -> dict[str, list[str]]:
    rows = rows if rows is not None else build()
    out: dict[str, list[str]] = {}
    for r in rows:
        if r["key_flag"]:
            out.setdefault(r["table"], []).append(r["field"])
    return out


def write(path: Path = CATALOG_PATH) -> int:
    rows = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))
    return len(rows)


if __name__ == "__main__":
    n = write()
    rows = build()
    checks = sum(1 for r in rows if r["check_table"])
    keys = sum(1 for r in rows if r["key_flag"])
    print(f"  {len(FIELDS)} tables, {n} fields, {keys} key fields, "
          f"{checks} declared check tables -> {CATALOG_PATH.name}")
