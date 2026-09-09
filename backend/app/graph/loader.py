"""Load the generated SAP tables into Neo4j.

Idempotent: every write is a MERGE on the node key, so re-running is safe.
Every node carries ``_source_table`` / ``_source_key`` and every relationship
carries ``_derived_from`` -- that is what makes the lineage trails real rather
than asserted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR, get_settings

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT supplier_key IF NOT EXISTS FOR (n:Supplier) REQUIRE n.lifnr IS UNIQUE",
    "CREATE CONSTRAINT material_key IF NOT EXISTS FOR (n:Material) REQUIRE n.matnr IS UNIQUE",
    "CREATE CONSTRAINT plant_key IF NOT EXISTS FOR (n:Plant) REQUIRE n.werks IS UNIQUE",
    "CREATE CONSTRAINT customer_key IF NOT EXISTS FOR (n:Customer) REQUIRE n.kunnr IS UNIQUE",
    "CREATE CONSTRAINT po_key IF NOT EXISTS FOR (n:PurchaseOrder) REQUIRE n.po_key IS UNIQUE",
    "CREATE CONSTRAINT sched_key IF NOT EXISTS FOR (n:ScheduleLine) REQUIRE n.sched_key IS UNIQUE",
    "CREATE CONSTRAINT bom_item_key IF NOT EXISTS FOR (n:BOMItem) REQUIRE n.bom_item_key IS UNIQUE",
    "CREATE CONSTRAINT prod_key IF NOT EXISTS FOR (n:ProductionOrder) REQUIRE n.aufnr IS UNIQUE",
    "CREATE CONSTRAINT resb_key IF NOT EXISTS FOR (n:Reservation) REQUIRE n.resb_key IS UNIQUE",
    "CREATE CONSTRAINT so_key IF NOT EXISTS FOR (n:SalesOrder) REQUIRE n.so_key IS UNIQUE",
    "CREATE CONSTRAINT dlv_key IF NOT EXISTS FOR (n:Delivery) REQUIRE n.vbeln IS UNIQUE",
]


def _read(name: str, data_dir: Path) -> list[dict]:
    return json.loads((data_dir / f"{name}.json").read_text())


def load(driver, data_dir: Path | None = None, wipe: bool = False) -> dict[str, int]:
    data_dir = data_dir or DATA_DIR
    t = {n: _read(n, data_dir) for n in (
        "plants", "suppliers", "customers", "materials", "material_plant",
        "material_stock", "source_list", "po_header", "po_item", "po_schedule",
        "bom_link", "bom_header", "bom_item",
        "prod_order_header", "prod_order_item", "reservations",
        "so_header", "so_item", "delivery_header", "delivery_item",
    )}

    cost = {m["MATNR"]: m["unit_cost"] for m in t["materials"]}
    marc = {(r["MATNR"], r["WERKS"]): r for r in t["material_plant"]}
    po_hdr = {r["EBELN"]: r for r in t["po_header"]}
    so_hdr = {r["VBELN"]: r for r in t["so_header"]}

    with driver.session() as s:
        if wipe:
            s.run("MATCH (n) DETACH DELETE n")
        for c in CONSTRAINTS:
            s.run(c)

        # ---- master data ------------------------------------------------
        s.run("""
            UNWIND $rows AS r
            MERGE (n:Plant {werks: r.WERKS})
            SET n.name = r.NAME1, n.country = r.LAND1, n.city = r.ORT01,
                n.idle_plant_cost_per_day = r.idle_plant_cost_per_day,
                n._source_table = 'T001W', n._source_key = 'WERKS=' + r.WERKS
        """, rows=t["plants"])

        s.run("""
            UNWIND $rows AS r
            MERGE (n:Supplier {lifnr: r.LIFNR})
            SET n.name = r.NAME1, n.country = r.LAND1, n.city = r.ORT01,
                n.risk_score = r.risk_score,
                n._source_table = 'LFA1', n._source_key = 'LIFNR=' + r.LIFNR
        """, rows=t["suppliers"])

        s.run("""
            UNWIND $rows AS r
            MERGE (n:Customer {kunnr: r.KUNNR})
            SET n.name = r.NAME1, n.country = r.LAND1, n.city = r.ORT01,
                n._source_table = 'KNA1', n._source_key = 'KUNNR=' + r.KUNNR
        """, rows=t["customers"])

        s.run("""
            UNWIND $rows AS r
            MERGE (n:Material {matnr: r.MATNR})
            SET n.name = r.MAKTX, n.material_type = r.MTART,
                n.material_group = r.MATKL, n.uom = r.MEINS,
                n.unit_cost = r.unit_cost,
                n._source_table = 'MARA', n._source_key = 'MATNR=' + r.MATNR
        """, rows=t["materials"])

        # ---- stock: Material -[:STOCKED_AT]-> Plant ----------------------
        stock_rows = [{
            "MATNR": r["MATNR"], "WERKS": r["WERKS"], "LGORT": r["LGORT"],
            "LABST": r["LABST"],
            "EISBE": marc.get((r["MATNR"], r["WERKS"]), {}).get("EISBE", 0.0),
            "PLIFZ": marc.get((r["MATNR"], r["WERKS"]), {}).get("PLIFZ", 0),
        } for r in t["material_stock"]]
        s.run("""
            UNWIND $rows AS r
            MATCH (m:Material {matnr: r.MATNR}), (p:Plant {werks: r.WERKS})
            MERGE (m)-[st:STOCKED_AT]->(p)
            SET st.on_hand = r.LABST, st.lgort = r.LGORT,
                st.safety_stock = r.EISBE, st.lead_time_days = r.PLIFZ,
                st._derived_from = 'MARD.WERKS -> T001W.WERKS',
                st._source_table = 'MARD'
        """, rows=stock_rows)

        # ---- source list: Supplier -[:SUPPLIES]-> Material ---------------
        s.run("""
            UNWIND $rows AS r
            MATCH (s:Supplier {lifnr: r.LIFNR}), (m:Material {matnr: r.MATNR})
            MERGE (s)-[x:SUPPLIES]->(m)
            SET x.net_price = r.NETPR, x.lead_time_days = r.APLFZ,
                x.is_primary = r.is_primary, x.unit_cost = r.unit_cost,
                x._derived_from = 'EINA.LIFNR -> LFA1.LIFNR',
                x._source_table = 'EINA/EINE'
        """, rows=t["source_list"])

        # ---- purchase orders ---------------------------------------------
        po_rows = [{
            "po_key": f"{i['EBELN']}/{i['EBELP']}", "EBELN": i["EBELN"],
            "EBELP": i["EBELP"], "MATNR": i["MATNR"], "TXZ01": i["TXZ01"],
            "WERKS": i["WERKS"], "MENGE": i["MENGE"], "NETPR": i["NETPR"],
            "NETWR": i["NETWR"], "LIFNR": po_hdr[i["EBELN"]]["LIFNR"],
            "BEDAT": po_hdr[i["EBELN"]]["BEDAT"],
        } for i in t["po_item"]]
        s.run("""
            UNWIND $rows AS r
            MERGE (n:PurchaseOrder {po_key: r.po_key})
            SET n.ebeln = r.EBELN, n.ebelp = r.EBELP, n.matnr = r.MATNR,
                n.material_name = r.TXZ01, n.werks = r.WERKS, n.menge = r.MENGE,
                n.net_price = r.NETPR, n.net_value = r.NETWR,
                n.lifnr = r.LIFNR, n.order_date = r.BEDAT,
                n._source_table = 'EKKO/EKPO',
                n._source_key = 'EBELN=' + r.EBELN + '/EBELP=' + r.EBELP
            WITH n, r
            MATCH (s:Supplier {lifnr: r.LIFNR})
            MERGE (s)-[f:FULFILLS]->(n)
            SET f._derived_from = 'EKKO.LIFNR -> LFA1.LIFNR'
            WITH n, r
            MATCH (m:Material {matnr: r.MATNR})
            MERGE (n)-[o:ORDERS]->(m)
            SET o._derived_from = 'EKPO.MATNR -> MARA.MATNR'
            WITH n, r
            MATCH (p:Plant {werks: r.WERKS})
            MERGE (n)-[dt:DELIVERED_TO]->(p)
            SET dt._derived_from = 'EKPO.WERKS -> T001W.WERKS'
        """, rows=po_rows)

        sched_rows = [{
            "sched_key": f"{r['EBELN']}/{r['EBELP']}/{r['ETENR']}",
            "po_key": f"{r['EBELN']}/{r['EBELP']}", "ETENR": r["ETENR"],
            "EINDT": r["EINDT"], "MENGE": r["MENGE"], "WEMNG": r["WEMNG"],
        } for r in t["po_schedule"]]
        s.run("""
            UNWIND $rows AS r
            MERGE (n:ScheduleLine {sched_key: r.sched_key})
            SET n.etenr = r.ETENR, n.delivery_date = r.EINDT,
                n.menge = r.MENGE, n.received_qty = r.WEMNG,
                n._source_table = 'EKET', n._source_key = r.sched_key
            WITH n, r
            MATCH (po:PurchaseOrder {po_key: r.po_key})
            MERGE (po)-[sa:SCHEDULED_AT]->(n)
            SET sa._derived_from = 'EKET.EBELN+EBELP -> EKPO.EBELN+EBELP'
        """, rows=sched_rows)

        # ---- bills of material -------------------------------------------
        # MAST names the BOM for a material at a plant, STKO carries the base
        # quantity the component quantities are stated against, STPO holds the
        # components. The three are joined here so one :BOMItem node answers
        # "what goes into this assembly, and how much" in a single read.
        stko = {(r["STLNR"], r["STLAL"]): r for r in t["bom_header"]}
        mast = {(r["STLNR"], r["STLAL"]): r for r in t["bom_link"]}
        bom_rows = []
        for item in t["bom_item"]:
            key = (item["STLNR"], item["STLAL"])
            link = mast.get(key)
            if not link:
                logger.warning("STPO row %s has no MAST link; skipped", key)
                continue
            bom_rows.append({
                "bom_item_key": f"{item['STLNR']}/{item['STLAL']}/{item['POSNR']}",
                "STLNR": item["STLNR"], "STLAL": item["STLAL"],
                "STLKN": item["STLKN"], "POSNR": item["POSNR"],
                "IDNRK": item["IDNRK"], "MENGE": item["MENGE"],
                "MEINS": item["MEINS"], "POSTP": item["POSTP"],
                "MATNR": link["MATNR"], "WERKS": link["WERKS"],
                "STLAN": link["STLAN"],
                "BMENG": stko.get(key, {}).get("BMENG", 1.0),
            })
        s.run("""
            UNWIND $rows AS r
            MERGE (n:BOMItem {bom_item_key: r.bom_item_key})
            SET n.stlnr = r.STLNR, n.stlal = r.STLAL, n.stlkn = r.STLKN,
                n.posnr = r.POSNR, n.idnrk = r.IDNRK, n.menge = r.MENGE,
                n.uom = r.MEINS, n.item_category = r.POSTP,
                n.parent_matnr = r.MATNR, n.werks = r.WERKS, n.stlan = r.STLAN,
                n.base_qty = r.BMENG,
                n._source_table = 'MAST/STKO/STPO',
                n._source_key = 'STLNR=' + r.STLNR + '/STLAL=' + r.STLAL
                                + '/POSNR=' + r.POSNR
            WITH n, r
            MATCH (c:Material {matnr: r.IDNRK})
            MERGE (c)-[co:COMPONENT_OF]->(n)
            SET co._derived_from = 'STPO.IDNRK -> MARA.MATNR',
                co._source_table = 'STPO'
            WITH n, r
            MATCH (p:Material {matnr: r.MATNR})
            MERGE (n)-[ai:ASSEMBLES_INTO]->(p)
            SET ai._derived_from = 'MAST.MATNR -> MARA.MATNR',
                ai._source_table = 'MAST'
        """, rows=bom_rows)

        # ---- production orders -------------------------------------------
        s.run("""
            UNWIND $rows AS r
            MERGE (n:ProductionOrder {aufnr: r.AUFNR})
            SET n.output_matnr = r.PLNBEZ, n.order_qty = r.GAMNG,
                n.scheduled_start = r.GSTRP, n.scheduled_finish = r.GLTRP,
                n.werks = r.WERKS,
                n._source_table = 'AFKO/AFPO', n._source_key = 'AUFNR=' + r.AUFNR
            WITH n, r
            MATCH (m:Material {matnr: r.PLNBEZ})
            MERGE (n)-[pr:PRODUCES]->(m)
            SET pr._derived_from = 'AFPO.MATNR -> MARA.MATNR'
            WITH n, r
            MATCH (p:Plant {werks: r.WERKS})
            MERGE (n)-[ra:RUNS_AT]->(p)
            SET ra._derived_from = 'AFKO.WERKS -> T001W.WERKS'
        """, rows=t["prod_order_header"])

        resb_rows = [{
            "resb_key": f"{r['RSNUM']}/{r['RSPOS']}", **r
        } for r in t["reservations"]]
        s.run("""
            UNWIND $rows AS r
            MERGE (n:Reservation {resb_key: r.resb_key})
            SET n.rsnum = r.RSNUM, n.rspos = r.RSPOS, n.aufnr = r.AUFNR,
                n.matnr = r.MATNR, n.werks = r.WERKS,
                n.required_qty = r.BDMNG, n.required_date = r.BDTER,
                n._source_table = 'RESB', n._source_key = r.resb_key
            WITH n, r
            MATCH (po:ProductionOrder {aufnr: r.AUFNR})
            MERGE (po)-[rq:REQUIRES]->(n)
            SET rq._derived_from = 'RESB.AUFNR -> AFKO.AUFNR'
            WITH n, r
            MATCH (m:Material {matnr: r.MATNR})
            MERGE (n)-[cs:CONSUMES]->(m)
            SET cs._derived_from = 'RESB.MATNR -> MARA.MATNR'
        """, rows=resb_rows)

        # ---- sales orders -------------------------------------------------
        so_rows = [{
            "so_key": f"{i['VBELN']}/{i['POSNR']}", "VBELN": i["VBELN"],
            "POSNR": i["POSNR"], "MATNR": i["MATNR"], "ARKTX": i["ARKTX"],
            "WERKS": i["WERKS"], "KWMENG": i["KWMENG"], "NETWR": i["NETWR"],
            "KUNNR": so_hdr[i["VBELN"]]["KUNNR"],
            "AUDAT": so_hdr[i["VBELN"]]["AUDAT"],
        } for i in t["so_item"]]
        s.run("""
            UNWIND $rows AS r
            MERGE (n:SalesOrder {so_key: r.so_key})
            SET n.vbeln = r.VBELN, n.posnr = r.POSNR, n.matnr = r.MATNR,
                n.material_name = r.ARKTX, n.werks = r.WERKS,
                n.order_qty = r.KWMENG, n.net_value = r.NETWR,
                n.kunnr = r.KUNNR, n.order_date = r.AUDAT,
                n._source_table = 'VBAK/VBAP',
                n._source_key = 'VBELN=' + r.VBELN + '/POSNR=' + r.POSNR
            WITH n, r
            MATCH (c:Customer {kunnr: r.KUNNR})
            MERGE (n)-[st:SOLD_TO]->(c)
            SET st._derived_from = 'VBAK.KUNNR -> KNA1.KUNNR'
            WITH n, r
            MATCH (m:Material {matnr: r.MATNR})
            MERGE (n)-[dm:DEMANDS]->(m)
            SET dm._derived_from = 'VBAP.MATNR -> MARA.MATNR'
        """, rows=so_rows)

        # ---- deliveries ---------------------------------------------------
        dlv_by_hdr = {}
        for li in t["delivery_item"]:
            dlv_by_hdr.setdefault(li["VBELN"], li)
        dlv_rows = [{
            **h,
            "VGBEL": dlv_by_hdr.get(h["VBELN"], {}).get("VGBEL"),
            "POSNR": dlv_by_hdr.get(h["VBELN"], {}).get("POSNR", "10"),
            "LFIMG": dlv_by_hdr.get(h["VBELN"], {}).get("LFIMG", 0.0),
            "NETWR": dlv_by_hdr.get(h["VBELN"], {}).get("NETWR", 0.0),
        } for h in t["delivery_header"]]
        s.run("""
            UNWIND $rows AS r
            MERGE (n:Delivery {vbeln: r.VBELN})
            SET n.kunnr = r.KUNNR, n.planned_goods_issue = r.LFDAT,
                n.vstel = r.VSTEL, n.penalty_rate = r.penalty_rate,
                n.ref_sales_order = r.VGBEL, n.posnr = r.POSNR,
                n.delivery_qty = r.LFIMG, n.net_value = r.NETWR,
                n._source_table = 'LIKP/LIPS', n._source_key = 'VBELN=' + r.VBELN
            WITH n, r
            MATCH (c:Customer {kunnr: r.KUNNR})
            MERGE (n)-[stc:SHIPS_TO]->(c)
            SET stc._derived_from = 'LIKP.KUNNR -> KNA1.KUNNR'
            WITH n, r
            MATCH (p:Plant {werks: r.VSTEL})
            MERGE (n)-[sf:SHIPS_FROM]->(p)
            SET sf._derived_from = 'LIKP.VSTEL -> T001W.WERKS'
        """, rows=dlv_rows)

        s.run("""
            UNWIND $rows AS r
            MATCH (d:Delivery {vbeln: r.VBELN})
            MATCH (so:SalesOrder {vbeln: r.VGBEL, posnr: r.VGPOS})
            MERGE (d)-[fo:FULFILLS_ORDER]->(so)
            SET fo._derived_from = 'LIPS.VGBEL -> VBAK.VBELN', fo._inferred = true
        """, rows=t["delivery_item"])

        counts = {
            r["label"]: r["c"] for r in s.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c"
            ).data()
        }
        rel_count = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        counts["_relationships"] = rel_count

    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    if not settings.neo4j_configured:
        raise SystemExit(
            "Neo4j is not configured.\n"
            "  Set NEO4J_URI and NEO4J_PASSWORD in backend/.env to load a real graph.\n"
            "  Without them the backend still runs on GRAPH_BACKEND=memory."
        )
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        driver.verify_connectivity()
        counts = load(driver, wipe=True)
        for k in sorted(counts):
            print(f"  {k:<20} {counts[k]:>6}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
