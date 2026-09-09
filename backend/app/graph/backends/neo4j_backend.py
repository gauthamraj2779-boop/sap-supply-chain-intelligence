"""Neo4j backend -- the production path.

Implements the identical semantic surface as MemoryBackend, in Cypher. Results
must match the memory backend exactly; tests/test_backend_parity.py enforces
that whenever credentials are present.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase

from app.graph.adapter import GraphBackend, GraphUnavailable

logger = logging.getLogger(__name__)


class Neo4jBackend(GraphBackend):
    name = "neo4j"

    def __init__(self, uri: str, user: str, password: str) -> None:
        self.uri, self.user, self.password = uri, user, password
        self._driver = None

    # -- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", self.uri)

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def _q(self, cypher: str, **params) -> list[dict[str, Any]]:
        if not self._driver:
            raise GraphUnavailable("Neo4j driver is not connected")
        with self._driver.session() as s:
            return [r.data() for r in s.run(cypher, **params)]

    @property
    def supports_cypher(self) -> bool:
        return True

    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        lowered = query.lower()
        forbidden = ("create", "merge", "delete", "set ", "remove", "drop",
                     "call db.", "call apoc", "load csv")
        for token in forbidden:
            if token in lowered:
                raise GraphUnavailable(
                    f"Read-only endpoint: '{token.strip()}' is not permitted."
                )
        return self._q(query, **(params or {}))

    def counts(self) -> dict[str, int]:
        rows = self._q(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY label"
        )
        return {r["label"]: r["c"] for r in rows}

    # -- master data ----------------------------------------------------
    def supplier(self, lifnr):
        r = self._q("MATCH (s:Supplier {lifnr:$lifnr}) RETURN s", lifnr=lifnr)
        if not r:
            return None
        s = r[0]["s"]
        return {"LIFNR": s["lifnr"], "NAME1": s["name"], "LAND1": s.get("country"),
                "ORT01": s.get("city"), "risk_score": s.get("risk_score", 0.5)}

    def suppliers(self):
        rows = self._q("MATCH (s:Supplier) RETURN s ORDER BY s.lifnr")
        return [{"LIFNR": r["s"]["lifnr"], "NAME1": r["s"]["name"],
                 "LAND1": r["s"].get("country"), "ORT01": r["s"].get("city"),
                 "risk_score": r["s"].get("risk_score", 0.5)} for r in rows]

    def material(self, matnr):
        r = self._q("MATCH (m:Material {matnr:$m}) RETURN m", m=matnr)
        if not r:
            return None
        m = r[0]["m"]
        return {"MATNR": m["matnr"], "MAKTX": m.get("name"),
                "MTART": m.get("material_type"), "MATKL": m.get("material_group"),
                "MEINS": m.get("uom", "EA"), "unit_cost": m.get("unit_cost", 0.0)}

    def plant(self, werks):
        r = self._q("MATCH (p:Plant {werks:$w}) RETURN p", w=werks)
        if not r:
            return None
        p = r[0]["p"]
        return {"WERKS": p["werks"], "NAME1": p.get("name"),
                "LAND1": p.get("country"), "ORT01": p.get("city"),
                "idle_plant_cost_per_day": p.get("idle_plant_cost_per_day", 0.0)}

    def customer(self, kunnr):
        r = self._q("MATCH (c:Customer {kunnr:$k}) RETURN c", k=kunnr)
        if not r:
            return None
        c = r[0]["c"]
        return {"KUNNR": c["kunnr"], "NAME1": c.get("name"),
                "LAND1": c.get("country"), "ORT01": c.get("city")}

    # -- procurement ----------------------------------------------------
    def open_schedule_lines_for_supplier(self, lifnr):
        rows = self._q(
            """
            MATCH (s:Supplier {lifnr:$lifnr})-[:FULFILLS]->(po:PurchaseOrder)
                  -[:SCHEDULED_AT]->(sl:ScheduleLine)
            WHERE coalesce(sl.received_qty, 0) < sl.menge
            RETURN po, sl ORDER BY sl.delivery_date
            """,
            lifnr=lifnr,
        )
        return [{
            "EBELN": r["po"]["ebeln"], "EBELP": r["po"]["ebelp"], "LIFNR": lifnr,
            "MATNR": r["po"]["matnr"], "TXZ01": r["po"].get("material_name", ""),
            "WERKS": r["po"]["werks"], "MENGE": float(r["po"]["menge"]),
            "NETPR": float(r["po"].get("net_price", 0.0)),
            "NETWR": float(r["po"]["net_value"]),
            "EINDT": r["sl"]["delivery_date"], "ETENR": r["sl"].get("etenr", "0001"),
        } for r in rows]

    def inbound_schedule_lines(self, matnr, werks, exclude_lifnr=None):
        rows = self._q(
            """
            MATCH (s:Supplier)-[:FULFILLS]->(po:PurchaseOrder)-[:SCHEDULED_AT]->(sl:ScheduleLine)
            WHERE po.matnr = $m AND po.werks = $w
              AND ($ex IS NULL OR s.lifnr <> $ex)
              AND coalesce(sl.received_qty, 0) < sl.menge
            RETURN s.lifnr AS lifnr, po, sl ORDER BY sl.delivery_date
            """,
            m=matnr, w=werks, ex=exclude_lifnr,
        )
        return [{
            "EBELN": r["po"]["ebeln"], "EBELP": r["po"]["ebelp"],
            "LIFNR": r["lifnr"], "MATNR": matnr, "WERKS": werks,
            "MENGE": float(r["sl"]["menge"]), "EINDT": r["sl"]["delivery_date"],
        } for r in rows]

    def alternate_sources(self, matnr, exclude_lifnr):
        rows = self._q(
            """
            MATCH (s:Supplier)-[r:SUPPLIES]->(m:Material {matnr:$m})
            WHERE s.lifnr <> $ex
            RETURN s, properties(r) AS r
            ORDER BY r.lead_time_days, r.net_price
            """,
            m=matnr, ex=exclude_lifnr,
        )
        return [{
            "MATNR": matnr, "LIFNR": r["s"]["lifnr"],
            "supplier_name": r["s"].get("name", r["s"]["lifnr"]),
            "NETPR": float(r["r"]["net_price"]),
            "APLFZ": int(r["r"]["lead_time_days"]),
            "is_primary": bool(r["r"].get("is_primary", False)),
            "unit_cost": float(r["r"].get("unit_cost", r["r"]["net_price"])),
            "risk_score": float(r["s"].get("risk_score", 0.5)),
        } for r in rows]

    # -- inventory ------------------------------------------------------
    # NOTE: relationship variables are always returned through properties().
    # neo4j's Record.data() renders a relationship as the tuple
    # (start_props, type, end_props), so `rel["field"]` raises TypeError. Nodes
    # serialise as plain dicts and need no wrapping.
    def stock(self, matnr, werks):
        r = self._q(
            """
            MATCH (m:Material {matnr:$m})-[st:STOCKED_AT]->(p:Plant {werks:$w})
            RETURN properties(st) AS st
            """,
            m=matnr, w=werks,
        )
        if not r:
            return None
        st = r[0]["st"]
        return {"MATNR": matnr, "WERKS": werks, "LABST": float(st["on_hand"]),
                "LGORT": st.get("lgort", "0001"),
                "EISBE": float(st.get("safety_stock", 0.0)),
                "PLIFZ": int(st.get("lead_time_days", 0))}

    def stock_all_plants(self, matnr):
        rows = self._q(
            """
            MATCH (m:Material {matnr:$m})-[st:STOCKED_AT]->(p:Plant)
            RETURN p.werks AS werks, properties(st) AS st ORDER BY p.werks
            """,
            m=matnr,
        )
        return [{"MATNR": matnr, "WERKS": r["werks"],
                 "LABST": float(r["st"]["on_hand"]),
                 "EISBE": float(r["st"].get("safety_stock", 0.0))} for r in rows]

    # -- bill of materials ----------------------------------------------
    @staticmethod
    def _bom_row(b, parent, component) -> dict[str, Any]:
        base = float(b.get("base_qty", 1.0)) or 1.0
        menge = float(b["menge"])
        return {
            "MATNR": b["parent_matnr"], "WERKS": b.get("werks", ""),
            "STLAN": b.get("stlan", "1"), "STLNR": b["stlnr"],
            "STLAL": b.get("stlal", "01"), "POSNR": b["posnr"],
            "IDNRK": b["idnrk"], "MENGE": menge, "MEINS": b.get("uom", "EA"),
            "BMENG": base, "qty_per_unit": menge / base,
            "component_name": (component or {}).get("name", b["idnrk"]),
            "component_type": (component or {}).get("material_type", ""),
            "parent_name": (parent or {}).get("name", b["parent_matnr"]),
            "parent_type": (parent or {}).get("material_type", ""),
        }

    def bom_for_material(self, matnr):
        rows = self._q(
            """
            MATCH (b:BOMItem)-[:ASSEMBLES_INTO]->(p:Material {matnr:$m})
            MATCH (c:Material)-[:COMPONENT_OF]->(b)
            RETURN b, p, c ORDER BY b.posnr
            """,
            m=matnr,
        )
        return [self._bom_row(r["b"], r["p"], r["c"]) for r in rows]

    def where_used(self, matnr):
        rows = self._q(
            """
            MATCH (c:Material {matnr:$m})-[:COMPONENT_OF]->(b:BOMItem)
                  -[:ASSEMBLES_INTO]->(p:Material)
            RETURN b, p, c ORDER BY p.matnr, b.posnr
            """,
            m=matnr,
        )
        return [self._bom_row(r["b"], r["p"], r["c"]) for r in rows]

    # -- production -----------------------------------------------------
    def reservations_for(self, matnr, werks):
        rows = self._q(
            """
            MATCH (po:ProductionOrder)-[:REQUIRES]->(r:Reservation)-[:CONSUMES]->(m:Material {matnr:$m})
            WHERE r.werks = $w
            RETURN r ORDER BY r.required_date
            """,
            m=matnr, w=werks,
        )
        return [{"RSNUM": r["r"]["rsnum"], "RSPOS": r["r"]["rspos"],
                 "AUFNR": r["r"]["aufnr"], "MATNR": matnr, "WERKS": werks,
                 "BDMNG": float(r["r"]["required_qty"]),
                 "BDTER": r["r"]["required_date"]} for r in rows]

    def production_order(self, aufnr):
        r = self._q("MATCH (po:ProductionOrder {aufnr:$a}) RETURN po", a=aufnr)
        if not r:
            return None
        po = r[0]["po"]
        return {"AUFNR": po["aufnr"], "PLNBEZ": po["output_matnr"],
                "WERKS": po["werks"], "GAMNG": float(po["order_qty"]),
                "GSTRP": po.get("scheduled_start"), "GLTRP": po["scheduled_finish"],
                "output_MATNR": po["output_matnr"]}

    def reservations_of_order(self, aufnr):
        rows = self._q(
            "MATCH (po:ProductionOrder {aufnr:$a})-[:REQUIRES]->(r:Reservation) RETURN r",
            a=aufnr,
        )
        return [{"RSNUM": r["r"]["rsnum"], "RSPOS": r["r"]["rspos"], "AUFNR": aufnr,
                 "MATNR": r["r"]["matnr"], "WERKS": r["r"]["werks"],
                 "BDMNG": float(r["r"]["required_qty"]),
                 "BDTER": r["r"]["required_date"]} for r in rows]

    # -- demand ---------------------------------------------------------
    def sales_items_for_material(self, matnr):
        rows = self._q(
            """
            MATCH (so:SalesOrder)-[:DEMANDS]->(m:Material {matnr:$m})
            OPTIONAL MATCH (so)-[:SOLD_TO]->(c:Customer)
            RETURN so, c
            """,
            m=matnr,
        )
        return [{
            "VBELN": r["so"]["vbeln"], "POSNR": r["so"]["posnr"], "MATNR": matnr,
            "ARKTX": r["so"].get("material_name", ""), "WERKS": r["so"].get("werks"),
            "KWMENG": float(r["so"]["order_qty"]), "NETWR": float(r["so"]["net_value"]),
            "KUNNR": (r["c"] or {}).get("kunnr", ""),
            "customer_name": (r["c"] or {}).get("name", ""),
            "AUDAT": r["so"].get("order_date"),
        } for r in rows]

    def deliveries_for_sales_order(self, vbeln):
        rows = self._q(
            """
            MATCH (d:Delivery)-[:FULFILLS_ORDER]->(so:SalesOrder {vbeln:$v})
            OPTIONAL MATCH (d)-[:SHIPS_TO]->(c:Customer)
            RETURN d, c
            """,
            v=vbeln,
        )
        return [{
            "VBELN": r["d"]["vbeln"], "KUNNR": (r["c"] or {}).get("kunnr", ""),
            "customer_name": (r["c"] or {}).get("name", ""),
            "LFDAT": r["d"]["planned_goods_issue"], "VSTEL": r["d"].get("vstel", ""),
            "VGBEL": vbeln, "POSNR": r["d"].get("posnr", "10"),
            "LFIMG": float(r["d"].get("delivery_qty", 0.0)),
            "NETWR": float(r["d"].get("net_value", 0.0)),
            "penalty_rate": float(r["d"].get("penalty_rate", 0.0)),
        } for r in rows]

    # -- visualisation --------------------------------------------------
    def graph_snapshot(self):
        nodes = self._q(
            """
            MATCH (n) RETURN elementId(n) AS eid, labels(n)[0] AS label,
                   coalesce(n.name, n.caption, n.matnr, n.ebeln, n.aufnr,
                            n.vbeln, n.werks, n.lifnr, n.kunnr) AS caption,
                   properties(n) AS props
            """
        )
        edges = self._q(
            """
            MATCH (a)-[r]->(b)
            RETURN elementId(a) AS source, elementId(b) AS target,
                   type(r) AS type, r._derived_from AS derived_from
            """
        )
        return (
            [{"id": n["eid"], "label": n["label"], "caption": n["caption"] or n["eid"],
              "properties": n["props"]} for n in nodes],
            edges,
        )
