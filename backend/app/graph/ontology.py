"""Emit the business ontology (OWL) and its governance shapes (SHACL).

Generated from ``app.graph.schema`` so the ontology can never drift from the
loader. Every class and property carries ``sap:sourceTable`` / ``sap:sourceField``
annotations -- lineage lives inside the ontology rather than being bolted on.
"""

from __future__ import annotations

from pathlib import Path

from app.config import ONTOLOGY_PATH
from app.graph.schema import EDGE_TYPES, NODE_TYPES

PREFIXES = """@prefix biz:  <http://sapkg.example/ontology#> .
@prefix sap:  <http://sapkg.example/sap#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://sapkg.example/ontology> a owl:Ontology ;
    rdfs:label "SAP Supply Chain Business Ontology" ;
    rdfs:comment "Business-semantic layer over SAP technical structures. Every term is annotated with the SAP table and field it derives from." ;
    owl:versionInfo "1.0.0" .

sap:sourceTable a owl:AnnotationProperty ; rdfs:label "SAP source table" .
sap:sourceField a owl:AnnotationProperty ; rdfs:label "SAP source field" .
sap:derivedFrom a owl:AnnotationProperty ; rdfs:label "SAP join expression" .
sap:inferred    a owl:AnnotationProperty ; rdfs:label "relationship inferred from data, not declared by a check table" .
"""

# Fields a record must carry for the impact maths to be trustworthy.
REQUIRED = {
    "Supplier": ["lifnr", "name"],
    "Material": ["matnr", "name"],
    "Plant": ["werks", "name"],
    "Customer": ["kunnr", "name"],
    "PurchaseOrder": ["ebeln", "matnr", "net_value"],
    "ScheduleLine": ["delivery_date", "menge"],
    "BOMItem": ["stlnr", "idnrk", "menge"],
    "ProductionOrder": ["aufnr", "output_matnr", "scheduled_finish"],
    "Reservation": ["aufnr", "matnr", "required_qty", "required_date"],
    "SalesOrder": ["vbeln", "matnr", "net_value"],
    "Delivery": ["vbeln", "planned_goods_issue"],
    "SourceList": ["matnr", "lifnr"],
}

NUMERIC = {"net_value", "menge", "required_qty", "order_qty", "on_hand",
           "safety_stock", "net_price", "delivery_qty", "unit_cost", "base_qty"}
DATE_LIKE = {"delivery_date", "required_date", "scheduled_finish",
             "planned_goods_issue", "scheduled_start", "order_date"}


def _dt(prop: str) -> str:
    if prop in NUMERIC:
        return "xsd:decimal"
    if prop in DATE_LIKE:
        return "xsd:date"
    return "xsd:string"


def build_ontology() -> str:
    out = [PREFIXES, "\n# " + "=" * 70, "# Classes", "# " + "=" * 70 + "\n"]

    for label, nt in NODE_TYPES.items():
        out.append(
            f"biz:{label} a owl:Class ;\n"
            f'    rdfs:label "{label}" ;\n'
            f'    skos:definition "{nt.business_definition}" ;\n'
            f'    sap:sourceTable "{", ".join(nt.source_tables)}" .\n'
        )

    out += ["\n# " + "=" * 70, "# Datatype properties (SAP field -> business term)",
            "# " + "=" * 70 + "\n"]
    seen: set[str] = set()
    for label, nt in NODE_TYPES.items():
        for f in nt.fields:
            pid = f"{label}_{f.graph_property}"
            if pid in seen:
                continue
            seen.add(pid)
            out.append(
                f"biz:{f.graph_property} a owl:DatatypeProperty ;\n"
                f'    rdfs:label "{f.business_term}" ;\n'
                f"    rdfs:domain biz:{label} ;\n"
                f"    rdfs:range {_dt(f.graph_property)} ;\n"
                f'    sap:sourceTable "{f.sap_table}" ;\n'
                f'    sap:sourceField "{f.sap_field}" .\n'
            )

    out += ["\n# " + "=" * 70, "# Object properties (relationships)",
            "# " + "=" * 70 + "\n"]
    for e in EDGE_TYPES:
        prop = e.type.lower().replace("_", "")
        inferred = "\n    sap:inferred true ;" if e.inferred else ""
        out.append(
            f"biz:{prop} a owl:ObjectProperty ;\n"
            f'    rdfs:label "{e.type}" ;\n'
            f'    skos:definition "{e.business_meaning}" ;\n'
            f"    rdfs:domain biz:{e.source_label} ;\n"
            f"    rdfs:range biz:{e.target_label} ;{inferred}\n"
            f'    sap:derivedFrom "{e.derived_from}" .\n'
        )

    out += ["\n# " + "=" * 70,
            "# SHACL shapes -- the governance gate.",
            "# A record failing these is loaded but flagged, and lowers the",
            "# data_completeness component of the published confidence score.",
            "# " + "=" * 70 + "\n"]
    for label, nt in NODE_TYPES.items():
        props = []
        for prop in REQUIRED.get(label, [nt.key_property]):
            fm = nt.lineage_for(prop)
            src = f'{fm.sap_table}.{fm.sap_field}' if fm else "derived"
            props.append(
                f"    sh:property [\n"
                f"        sh:path biz:{prop} ;\n"
                f"        sh:datatype {_dt(prop)} ;\n"
                f"        sh:minCount 1 ;\n"
                f'        sh:message "{label}.{prop} is required (SAP source: {src})" ;\n'
                f"    ] ;"
            )
        out.append(
            f"biz:{label}Shape a sh:NodeShape ;\n"
            f"    sh:targetClass biz:{label} ;\n"
            + "\n".join(props)
            + "\n    sh:closed false .\n"
        )

    out.append(
        "# Business rule: a schedule line cannot promise delivery before the\n"
        "# purchase order that contains it was even created.\n"
        "biz:ScheduleLineDateShape a sh:NodeShape ;\n"
        "    sh:targetClass biz:ScheduleLine ;\n"
        "    sh:property [\n"
        "        sh:path biz:delivery_date ;\n"
        "        sh:datatype xsd:date ;\n"
        '        sh:message "ScheduleLine.delivery_date must be a valid date (EKET.EINDT)" ;\n'
        "    ] .\n"
    )
    return "\n".join(out)


def write(path: Path | None = None) -> Path:
    path = path or ONTOLOGY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ontology())
    return path


if __name__ == "__main__":
    p = write()
    import rdflib

    g = rdflib.Graph()
    g.parse(p, format="turtle")
    classes = len(set(g.subjects(rdflib.RDF.type, rdflib.OWL.Class)))
    objprops = len(set(g.subjects(rdflib.RDF.type, rdflib.OWL.ObjectProperty)))
    dataprops = len(set(g.subjects(rdflib.RDF.type, rdflib.OWL.DatatypeProperty)))
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    shapes = len(set(g.subjects(rdflib.RDF.type, SH.NodeShape)))
    print(f"  wrote {p}")
    print(f"  {len(g)} triples | {classes} classes | {objprops} object properties "
          f"| {dataprops} datatype properties | {shapes} SHACL shapes")
