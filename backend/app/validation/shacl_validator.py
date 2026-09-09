"""SHACL validation -- the governance gate.

Projects the loaded records into RDF and validates them against the shapes in
ontology.ttl. Violations do not block the load; they are surfaced and they pull
down the ``data_completeness`` component of the published confidence score, so
a data-quality problem shows up as reduced confidence rather than a silently
wrong number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import ONTOLOGY_PATH

logger = logging.getLogger(__name__)

BIZ = "http://sapkg.example/ontology#"


@dataclass
class ValidationReport:
    conforms: bool = True
    nodes_validated: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    by_shape: dict[str, int] = field(default_factory=dict)
    available: bool = True
    note: str = ""

    @property
    def completeness(self) -> float:
        if not self.nodes_validated:
            return 1.0
        return max(0.0, 1.0 - len(self.violations) / self.nodes_validated)


_LABEL_FIELDS = {
    "Supplier": ("lifnr", "name"),
    "Material": ("matnr", "name"),
    "Plant": ("werks", "name"),
    "Customer": ("kunnr", "name"),
}


def validate(backend, sample_limit: int = 400) -> ValidationReport:
    """Validate master data plus a transactional slice against the shapes."""
    try:
        from pyshacl import validate as shacl_validate
        from rdflib import RDF, Graph, Literal, Namespace, URIRef
    except ImportError:  # pragma: no cover
        return ValidationReport(available=False, note="pyshacl/rdflib not installed")

    if not ONTOLOGY_PATH.exists():
        from app.graph.ontology import write as write_ontology

        write_ontology()

    from decimal import Decimal

    from rdflib.namespace import XSD

    biz = Namespace(BIZ)
    data = Graph()
    data.bind("biz", biz)
    n = 0

    # The shapes declare xsd:decimal / xsd:date, so the projection must emit
    # typed literals. Untyped strings would fail sh:datatype and report as data
    # quality problems that are really projection bugs.
    numeric = {"required_qty", "net_value", "menge", "order_qty", "on_hand",
               "safety_stock", "net_price", "delivery_qty", "unit_cost",
               "base_qty"}
    dates = {"required_date", "scheduled_finish", "planned_goods_issue",
             "delivery_date", "scheduled_start", "order_date"}

    def lit(key, value):
        if key in numeric:
            # pyshacl checks the Python value type behind the literal, so an
            # xsd:decimal must be built from Decimal -- a float yields
            # xsd:double semantics and fails sh:datatype.
            return Literal(Decimal(str(float(value))), datatype=XSD.decimal)
        if key in dates:
            return Literal(str(value)[:10], datatype=XSD.date)
        return Literal(str(value), datatype=XSD.string)

    def emit(cls: str, key: str, props: dict) -> None:
        nonlocal n
        subj = URIRef(f"{BIZ}{cls}/{key}")
        data.add((subj, RDF.type, biz[cls]))
        for k, v in props.items():
            if v is not None and v != "":
                data.add((subj, biz[k], lit(k, v)))
        n += 1

    try:
        for s in backend.suppliers()[:sample_limit]:
            emit("Supplier", s["LIFNR"], {"lifnr": s["LIFNR"], "name": s.get("NAME1")})

        raw = getattr(backend, "t", None)
        if raw:  # memory backend exposes the underlying tables directly
            for m in raw["materials"][:sample_limit]:
                emit("Material", m["MATNR"], {"matnr": m["MATNR"], "name": m.get("MAKTX")})
            for p in raw["plants"][:sample_limit]:
                emit("Plant", p["WERKS"], {"werks": p["WERKS"], "name": p.get("NAME1")})
            for c in raw["customers"][:sample_limit]:
                emit("Customer", c["KUNNR"], {"kunnr": c["KUNNR"], "name": c.get("NAME1")})
            for r in raw["reservations"][:sample_limit]:
                emit("Reservation", f"{r['RSNUM']}-{r['RSPOS']}", {
                    "aufnr": r["AUFNR"], "matnr": r["MATNR"],
                    "required_qty": float(r["BDMNG"]), "required_date": r["BDTER"],
                })
            for b in raw["bom_item"][:sample_limit]:
                emit("BOMItem", f"{b['STLNR']}-{b['POSNR']}", {
                    "stlnr": b["STLNR"], "posnr": b["POSNR"],
                    "idnrk": b["IDNRK"], "menge": float(b["MENGE"]),
                })
            for a in raw["prod_order_header"][:sample_limit]:
                emit("ProductionOrder", a["AUFNR"], {
                    "aufnr": a["AUFNR"], "output_matnr": a["PLNBEZ"],
                    "scheduled_finish": a["GLTRP"],
                })
            for dv in raw["delivery_header"][:sample_limit]:
                emit("Delivery", dv["VBELN"], {
                    "vbeln": dv["VBELN"], "planned_goods_issue": dv["LFDAT"],
                })

        shapes = Graph()
        shapes.parse(ONTOLOGY_PATH, format="turtle")
        conforms, results_graph, _text = shacl_validate(
            data, shacl_graph=shapes, inference="none",
            abort_on_first=False, meta_shacl=False, advanced=False,
        )

        SH = Namespace("http://www.w3.org/ns/shacl#")
        violations, by_shape = [], {}
        for res in results_graph.subjects(RDF.type, SH.ValidationResult):
            focus = str(results_graph.value(res, SH.focusNode) or "")
            path = str(results_graph.value(res, SH.resultPath) or "")
            msg = str(results_graph.value(res, SH.resultMessage) or "")
            shape = focus.rsplit("/", 1)[0].split("#")[-1] or "unknown"
            violations.append({
                "shape": shape, "focus_node": focus.split("#")[-1],
                "path": path.split("#")[-1], "message": msg,
            })
            by_shape[shape] = by_shape.get(shape, 0) + 1

        return ValidationReport(
            conforms=bool(conforms), nodes_validated=n,
            violations=violations[:100], by_shape=by_shape,
            note=(f"{n} nodes validated against {len(set(shapes.subjects()))} shape "
                  f"definitions in ontology.ttl"),
        )
    except Exception as exc:
        logger.warning("SHACL validation failed: %s", exc)
        return ValidationReport(available=False, note=f"validation error: {exc}")
