"""Graph, ontology and governance endpoints (feed the frontend's explorer tabs)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import ONTOLOGY_PATH
from app.graph.schema import BLAST_RADIUS_HOPS, EDGE_TYPES, NODE_TYPES

router = APIRouter(tags=["graph"])


@router.get("/graph")
def snapshot(request: Request) -> dict:
    nodes, edges = request.app.state.backend.graph_snapshot()
    return {"nodes": nodes, "edges": edges,
            "counts": {"nodes": len(nodes), "edges": len(edges)}}


@router.get("/schema")
def schema() -> dict:
    """The technical->business mapping, so the UI never hardcodes SAP names."""
    return {
        "node_types": [
            {
                "label": nt.label, "source_tables": list(nt.source_tables),
                "key": nt.key_property, "definition": nt.business_definition,
                "fields": [
                    {"sap_table": f.sap_table, "sap_field": f.sap_field,
                     "graph_property": f.graph_property, "business_term": f.business_term}
                    for f in nt.fields
                ],
            }
            for nt in NODE_TYPES.values()
        ],
        "edge_types": [
            {"type": e.type, "from": e.source_label, "to": e.target_label,
             "derived_from": e.derived_from, "meaning": e.business_meaning,
             "inferred": e.inferred}
            for e in EDGE_TYPES
        ],
        "blast_radius_hops": list(BLAST_RADIUS_HOPS),
    }


@router.get("/ontology")
def ontology() -> dict:
    if not ONTOLOGY_PATH.exists():
        from app.graph.ontology import write

        write()
    text = ONTOLOGY_PATH.read_text()
    return {"format": "text/turtle", "path": str(ONTOLOGY_PATH),
            "bytes": len(text), "content": text}


@router.get("/validation")
def validation(request: Request) -> dict:
    report = getattr(request.app.state, "shacl_report", None)
    if report is None:
        from app.validation import validate

        report = validate(request.app.state.backend)
        request.app.state.shacl_report = report
    return {
        "available": report.available, "conforms": report.conforms,
        "nodes_validated": report.nodes_validated,
        "completeness": round(report.completeness, 4),
        "violation_count": len(report.violations),
        "by_shape": report.by_shape, "violations": report.violations,
        "note": report.note,
    }


@router.get("/lineage/{node_type}/{node_id}")
def lineage(node_type: str, node_id: str) -> dict:
    """SAP table/field provenance for one node type."""
    nt = NODE_TYPES.get(node_type)
    if not nt:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown node type '{node_type}'. Known: {', '.join(NODE_TYPES)}",
        )
    return {
        "node_type": node_type, "node_id": node_id,
        "source_tables": list(nt.source_tables),
        "definition": nt.business_definition,
        "fields": [
            {"sap_table": f.sap_table, "sap_field": f.sap_field,
             "graph_property": f.graph_property, "business_term": f.business_term}
            for f in nt.fields
        ],
    }
