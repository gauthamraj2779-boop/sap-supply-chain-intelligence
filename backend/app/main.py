"""FastAPI application entry point.

Startup contract: the service must come up and serve useful results even when
nothing external is configured. The graph backend falls back to the in-process
store, the LLM degrades to silence, and /api/health reports exactly which
capabilities are live.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.graph.adapter import build_backend
from app.routers import discovery as discovery_router
from app.routers import graph as graph_router
from app.routers import health, impact, query

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sapkg")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    app.state.backend = build_backend(settings)
    logger.info(
        "Graph backend '%s' ready (%d records)",
        app.state.backend.name, sum(app.state.backend.counts().values()),
    )

    # Ensure the ontology exists, then run the governance gate once at startup
    # so every request can reuse the report instead of re-validating.
    try:
        from app.graph.ontology import write as write_ontology
        from app.validation import validate

        write_ontology()
        app.state.shacl_report = validate(app.state.backend)
        logger.info(
            "SHACL: conforms=%s, %d nodes validated, %d violations",
            app.state.shacl_report.conforms,
            app.state.shacl_report.nodes_validated,
            len(app.state.shacl_report.violations),
        )
    except Exception as exc:
        logger.warning("Startup validation skipped: %s", exc)
        app.state.shacl_report = None

    from app.engines.llm import get_llm

    st = get_llm().status()
    logger.info(
        "LLM: provider=%s model=%s available=%s (%s)",
        st.provider, st.model, st.available, st.reason,
    )
    if not st.available:
        logger.info(
            "Running deterministic-only: all financial figures, impact analysis "
            "and avoidance planning are fully available; prose narrative is not."
        )

    yield

    app.state.backend.close()


app = FastAPI(
    title="SAP Knowledge Graph - Self-Healing Supply Chain Intelligence",
    version="1.0.0",
    description=(
        "Multi-hop supplier-delay impact analysis over an SAP-derived knowledge "
        "graph, with dollar-denominated exposure, preventive avoidance planning, "
        "SAP source lineage and explainable confidence.\n\n"
        "**Architecture note:** every monetary figure is computed deterministically "
        "from graph records. The LLM phrases results and parses questions; it never "
        "produces a number. Narrative figures are cross-checked against computed "
        "values and the computed values always win."
    ),
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(impact.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(graph_router.router, prefix="/api")
app.include_router(discovery_router.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "service": "sap-knowledge-graph",
        "docs": "/docs",
        "endpoints": [
            "GET  /api/health", "GET  /api/suppliers", "POST /api/impact",
            "POST /api/query", "GET  /api/query/examples", "POST /api/cypher",
            "GET  /api/graph", "GET  /api/schema", "GET  /api/ontology",
            "GET  /api/validation", "GET  /api/lineage/{node_type}/{node_id}",
            "GET  /api/discovery", "GET  /api/discovery/profile",
        ],
    }
