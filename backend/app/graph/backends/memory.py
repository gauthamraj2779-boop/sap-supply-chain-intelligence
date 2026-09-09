"""In-process graph backend.

Serves the same semantic surface as Neo4j by indexing the generated SAP tables.
This is the default so the system always runs: no database, no credentials, no
network. It is also what makes every engine unit-testable.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.graph.adapter import GraphBackend, GraphUnavailable

_TABLES = (
    "plants", "suppliers", "customers", "materials", "material_plant",
    "material_stock", "source_list", "po_header", "po_item", "po_schedule",
    "prod_order_header", "prod_order_item", "reservations",
    "so_header", "so_item", "delivery_header", "delivery_item",
)


class MemoryBackend(GraphBackend):
    name = "memory"

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        self.t: dict[str, list[dict]] = {}
        self.meta: dict[str, Any] = {}
        self._idx: dict[str, Any] = {}
        self._connected = False

    # -- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        missing = [t for t in _TABLES if not (self.data_dir / f"{t}.json").exists()]
        if missing:
            raise GraphUnavailable(
                f"Synthetic data not generated (missing: {', '.join(missing[:3])}...). "
                "Run: python -m data.synthetic.generate_sap_data"
            )
        for t in _TABLES:
            self.t[t] = json.loads((self.data_dir / f"{t}.json").read_text())
        meta_path = self.data_dir / "meta.json"
        self.meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        self._build_indexes()
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def _build_indexes(self) -> None:
        i: dict[str, Any] = {}
        i["supplier"] = {r["LIFNR"]: r for r in self.t["suppliers"]}
        i["material"] = {r["MATNR"]: r for r in self.t["materials"]}
        i["plant"] = {r["WERKS"]: r for r in self.t["plants"]}
        i["customer"] = {r["KUNNR"]: r for r in self.t["customers"]}
        i["po_header"] = {r["EBELN"]: r for r in self.t["po_header"]}
        i["prod_header"] = {r["AUFNR"]: r for r in self.t["prod_order_header"]}
        i["prod_item"] = {r["AUFNR"]: r for r in self.t["prod_order_item"]}
        i["so_header"] = {r["VBELN"]: r for r in self.t["so_header"]}

        i["stock"] = {(r["MATNR"], r["WERKS"]): r for r in self.t["material_stock"]}
        i["marc"] = {(r["MATNR"], r["WERKS"]): r for r in self.t["material_plant"]}

        stock_by_mat = defaultdict(list)
        for r in self.t["material_stock"]:
            stock_by_mat[r["MATNR"]].append(r)
        i["stock_by_mat"] = dict(stock_by_mat)

        po_items = defaultdict(list)
        for r in self.t["po_item"]:
            po_items[r["EBELN"]].append(r)
        i["po_items"] = dict(po_items)

        sched = {}
        for r in self.t["po_schedule"]:
            sched[(r["EBELN"], r["EBELP"])] = r
        i["schedule"] = sched

        resb_by_mat = defaultdict(list)
        resb_by_order = defaultdict(list)
        for r in self.t["reservations"]:
            resb_by_mat[(r["MATNR"], r["WERKS"])].append(r)
            resb_by_order[r["AUFNR"]].append(r)
        i["resb_by_mat"] = dict(resb_by_mat)
        i["resb_by_order"] = dict(resb_by_order)

        so_by_mat = defaultdict(list)
        for r in self.t["so_item"]:
            so_by_mat[r["MATNR"]].append(r)
        i["so_by_mat"] = dict(so_by_mat)

        dlv_items_by_so = defaultdict(list)
        for r in self.t["delivery_item"]:
            dlv_items_by_so[r["VGBEL"]].append(r)
        i["dlv_items_by_so"] = dict(dlv_items_by_so)
        i["dlv_header"] = {r["VBELN"]: r for r in self.t["delivery_header"]}

        src_by_mat = defaultdict(list)
        for r in self.t["source_list"]:
            src_by_mat[r["MATNR"]].append(r)
        i["src_by_mat"] = dict(src_by_mat)

        prod_by_output = defaultdict(list)
        for r in self.t["prod_order_item"]:
            prod_by_output[r["MATNR"]].append(r)
        i["prod_by_output"] = dict(prod_by_output)

        self._idx = i

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.t.items()}

    # -- master data ----------------------------------------------------
    def supplier(self, lifnr):
        return self._idx["supplier"].get(lifnr)

    def suppliers(self):
        return list(self.t["suppliers"])

    def material(self, matnr):
        return self._idx["material"].get(matnr)

    def plant(self, werks):
        return self._idx["plant"].get(werks)

    def customer(self, kunnr):
        return self._idx["customer"].get(kunnr)

    # -- procurement ----------------------------------------------------
    def open_schedule_lines_for_supplier(self, lifnr):
        out = []
        for hdr in self.t["po_header"]:
            if hdr["LIFNR"] != lifnr:
                continue
            for item in self._idx["po_items"].get(hdr["EBELN"], []):
                sched = self._idx["schedule"].get((item["EBELN"], item["EBELP"]))
                if not sched:
                    continue
                # "Open" == goods receipt quantity still below ordered quantity.
                if float(sched.get("WEMNG", 0)) >= float(sched["MENGE"]):
                    continue
                out.append({
                    "EBELN": item["EBELN"], "EBELP": item["EBELP"],
                    "LIFNR": lifnr, "MATNR": item["MATNR"],
                    "TXZ01": item.get("TXZ01", ""), "WERKS": item["WERKS"],
                    "MENGE": float(item["MENGE"]), "NETPR": float(item["NETPR"]),
                    "NETWR": float(item["NETWR"]), "EINDT": sched["EINDT"],
                    "ETENR": sched["ETENR"],
                })
        return sorted(out, key=lambda r: r["EINDT"])

    def inbound_schedule_lines(self, matnr, werks, exclude_lifnr=None):
        out = []
        for hdr in self.t["po_header"]:
            if exclude_lifnr and hdr["LIFNR"] == exclude_lifnr:
                continue
            for item in self._idx["po_items"].get(hdr["EBELN"], []):
                if item["MATNR"] != matnr or item["WERKS"] != werks:
                    continue
                sched = self._idx["schedule"].get((item["EBELN"], item["EBELP"]))
                if not sched or float(sched.get("WEMNG", 0)) >= float(sched["MENGE"]):
                    continue
                out.append({
                    "EBELN": item["EBELN"], "EBELP": item["EBELP"],
                    "LIFNR": hdr["LIFNR"], "MATNR": matnr, "WERKS": werks,
                    "MENGE": float(sched["MENGE"]), "EINDT": sched["EINDT"],
                })
        return sorted(out, key=lambda r: r["EINDT"])

    def alternate_sources(self, matnr, exclude_lifnr):
        out = []
        for r in self._idx["src_by_mat"].get(matnr, []):
            if r["LIFNR"] == exclude_lifnr:
                continue
            sup = self.supplier(r["LIFNR"]) or {}
            out.append({
                "MATNR": matnr, "LIFNR": r["LIFNR"],
                "supplier_name": sup.get("NAME1", r["LIFNR"]),
                "NETPR": float(r["NETPR"]), "APLFZ": int(r["APLFZ"]),
                "is_primary": bool(r.get("is_primary")),
                "unit_cost": float(r.get("unit_cost", r["NETPR"])),
                "risk_score": float(sup.get("risk_score", 0.5)),
            })
        return sorted(out, key=lambda r: (r["APLFZ"], r["NETPR"]))

    # -- inventory ------------------------------------------------------
    def stock(self, matnr, werks):
        mard = self._idx["stock"].get((matnr, werks))
        if not mard:
            return None
        marc = self._idx["marc"].get((matnr, werks), {})
        return {
            "MATNR": matnr, "WERKS": werks,
            "LABST": float(mard["LABST"]), "LGORT": mard.get("LGORT", "0001"),
            "EISBE": float(marc.get("EISBE", 0.0)),
            "PLIFZ": int(marc.get("PLIFZ", 0)),
        }

    def stock_all_plants(self, matnr):
        out = []
        for mard in self._idx["stock_by_mat"].get(matnr, []):
            marc = self._idx["marc"].get((matnr, mard["WERKS"]), {})
            out.append({
                "MATNR": matnr, "WERKS": mard["WERKS"],
                "LABST": float(mard["LABST"]),
                "EISBE": float(marc.get("EISBE", 0.0)),
            })
        return out

    # -- production -----------------------------------------------------
    def reservations_for(self, matnr, werks):
        rows = self._idx["resb_by_mat"].get((matnr, werks), [])
        return sorted(
            [{
                "RSNUM": r["RSNUM"], "RSPOS": r["RSPOS"], "AUFNR": r["AUFNR"],
                "MATNR": r["MATNR"], "WERKS": r["WERKS"],
                "BDMNG": float(r["BDMNG"]), "BDTER": r["BDTER"],
            } for r in rows],
            key=lambda r: r["BDTER"],
        )

    def production_order(self, aufnr):
        hdr = self._idx["prod_header"].get(aufnr)
        if not hdr:
            return None
        item = self._idx["prod_item"].get(aufnr, {})
        return {
            "AUFNR": aufnr, "PLNBEZ": hdr["PLNBEZ"], "WERKS": hdr["WERKS"],
            "GAMNG": float(hdr["GAMNG"]), "GSTRP": hdr["GSTRP"],
            "GLTRP": hdr["GLTRP"], "output_MATNR": item.get("MATNR", hdr["PLNBEZ"]),
        }

    def reservations_of_order(self, aufnr):
        return [{
            "RSNUM": r["RSNUM"], "RSPOS": r["RSPOS"], "AUFNR": aufnr,
            "MATNR": r["MATNR"], "WERKS": r["WERKS"],
            "BDMNG": float(r["BDMNG"]), "BDTER": r["BDTER"],
        } for r in self._idx["resb_by_order"].get(aufnr, [])]

    # -- demand ---------------------------------------------------------
    def sales_items_for_material(self, matnr):
        out = []
        for item in self._idx["so_by_mat"].get(matnr, []):
            hdr = self._idx["so_header"].get(item["VBELN"], {})
            kunnr = hdr.get("KUNNR", "")
            cust = self.customer(kunnr) or {}
            out.append({
                "VBELN": item["VBELN"], "POSNR": item["POSNR"], "MATNR": matnr,
                "ARKTX": item.get("ARKTX", ""), "WERKS": item["WERKS"],
                "KWMENG": float(item["KWMENG"]), "NETWR": float(item["NETWR"]),
                "KUNNR": kunnr, "customer_name": cust.get("NAME1", kunnr),
                "AUDAT": hdr.get("AUDAT"),
            })
        return out

    def deliveries_for_sales_order(self, vbeln):
        out = []
        for li in self._idx["dlv_items_by_so"].get(vbeln, []):
            hdr = self._idx["dlv_header"].get(li["VBELN"])
            if not hdr:
                continue
            cust = self.customer(hdr["KUNNR"]) or {}
            out.append({
                "VBELN": hdr["VBELN"], "KUNNR": hdr["KUNNR"],
                "customer_name": cust.get("NAME1", hdr["KUNNR"]),
                "LFDAT": hdr["LFDAT"], "VSTEL": hdr.get("VSTEL", ""),
                "VGBEL": li["VGBEL"], "POSNR": li["POSNR"],
                "LFIMG": float(li["LFIMG"]), "NETWR": float(li.get("NETWR", 0.0)),
                "penalty_rate": float(hdr.get("penalty_rate", 0.0)),
            })
        return out

    def production_orders_producing(self, matnr):
        return [self.production_order(r["AUFNR"])
                for r in self._idx["prod_by_output"].get(matnr, [])]

    # -- visualisation --------------------------------------------------
    def graph_snapshot(self):
        nodes, edges = [], []

        def add(nid, label, caption, props=None):
            nodes.append({"id": nid, "label": label, "caption": caption,
                          "properties": props or {}})

        for s in self.t["suppliers"]:
            add(f"Supplier:{s['LIFNR']}", "Supplier", s["NAME1"],
                {"lifnr": s["LIFNR"], "country": s["LAND1"]})
        for p in self.t["plants"]:
            add(f"Plant:{p['WERKS']}", "Plant", p["NAME1"], {"werks": p["WERKS"]})
        for c in self.t["customers"]:
            add(f"Customer:{c['KUNNR']}", "Customer", c["NAME1"], {"kunnr": c["KUNNR"]})
        for m in self.t["materials"]:
            add(f"Material:{m['MATNR']}", "Material", m["MAKTX"],
                {"matnr": m["MATNR"], "type": m["MTART"]})
        for h in self.t["po_header"]:
            for it in self._idx["po_items"].get(h["EBELN"], []):
                nid = f"PurchaseOrder:{it['EBELN']}/{it['EBELP']}"
                add(nid, "PurchaseOrder", f"PO {it['EBELN']}-{it['EBELP']}",
                    {"ebeln": it["EBELN"], "net_value": it["NETWR"]})
                edges.append({"source": f"Supplier:{h['LIFNR']}", "target": nid,
                              "type": "FULFILLS", "derived_from": "EKKO.LIFNR -> LFA1.LIFNR"})
                edges.append({"source": nid, "target": f"Material:{it['MATNR']}",
                              "type": "ORDERS", "derived_from": "EKPO.MATNR -> MARA.MATNR"})
                edges.append({"source": nid, "target": f"Plant:{it['WERKS']}",
                              "type": "DELIVERED_TO", "derived_from": "EKPO.WERKS -> T001W.WERKS"})
        for a in self.t["prod_order_header"]:
            nid = f"ProductionOrder:{a['AUFNR']}"
            add(nid, "ProductionOrder", f"Prod {a['AUFNR']}",
                {"aufnr": a["AUFNR"], "output": a["PLNBEZ"]})
            edges.append({"source": nid, "target": f"Material:{a['PLNBEZ']}",
                          "type": "PRODUCES", "derived_from": "AFPO.MATNR -> MARA.MATNR"})
            edges.append({"source": nid, "target": f"Plant:{a['WERKS']}",
                          "type": "RUNS_AT", "derived_from": "AFKO.WERKS -> T001W.WERKS"})
        for r in self.t["reservations"]:
            edges.append({"source": f"ProductionOrder:{r['AUFNR']}",
                          "target": f"Material:{r['MATNR']}",
                          "type": "CONSUMES", "derived_from": "RESB.MATNR -> MARA.MATNR"})
        for h in self.t["so_header"]:
            nid = f"SalesOrder:{h['VBELN']}"
            add(nid, "SalesOrder", f"SO {h['VBELN']}",
                {"vbeln": h["VBELN"], "net_value": h["NETWR"]})
            edges.append({"source": nid, "target": f"Customer:{h['KUNNR']}",
                          "type": "SOLD_TO", "derived_from": "VBAK.KUNNR -> KNA1.KUNNR"})
        for it in self.t["so_item"]:
            edges.append({"source": f"SalesOrder:{it['VBELN']}",
                          "target": f"Material:{it['MATNR']}",
                          "type": "DEMANDS", "derived_from": "VBAP.MATNR -> MARA.MATNR"})
        for h in self.t["delivery_header"]:
            nid = f"Delivery:{h['VBELN']}"
            add(nid, "Delivery", f"Dlv {h['VBELN']}",
                {"vbeln": h["VBELN"], "lfdat": h["LFDAT"]})
            edges.append({"source": nid, "target": f"Customer:{h['KUNNR']}",
                          "type": "SHIPS_TO", "derived_from": "LIKP.KUNNR -> KNA1.KUNNR"})
        for li in self.t["delivery_item"]:
            edges.append({"source": f"Delivery:{li['VBELN']}",
                          "target": f"SalesOrder:{li['VGBEL']}",
                          "type": "FULFILLS_ORDER", "derived_from": "LIPS.VGBEL -> VBAK.VBELN"})
        for s in self.t["source_list"]:
            edges.append({"source": f"Supplier:{s['LIFNR']}",
                          "target": f"Material:{s['MATNR']}",
                          "type": "SUPPLIES", "derived_from": "EINA.LIFNR -> LFA1.LIFNR"})
        for m in self.t["material_stock"]:
            edges.append({"source": f"Material:{m['MATNR']}",
                          "target": f"Plant:{m['WERKS']}",
                          "type": "STOCKED_AT", "derived_from": "MARD.WERKS -> T001W.WERKS"})
        return nodes, edges
