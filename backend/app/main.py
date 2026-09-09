"""FastAPI application entry point.

Startup contract: the service must come up and serve useful results even when
nothing external is configured. The graph backend falls back to the in-process
store, the LLM degrades to silence, and /api/health reports exactly which
capabilities are live.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.graph.adapter import build_backend
from app.routers import agent as agent_router
from app.routers import discovery as discovery_router
from app.routers import graph as graph_router
from app.routers import health, impact, query

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sapkg")


def _ensure_data_is_current() -> None:
    """Regenerate the dataset if it was built for an earlier day.

    Every date in the data is relative to the day it was generated, so a
    deployed instance would otherwise show a supplier delay whose schedule
    lines are already in the past. Regeneration is deterministic, so this
    changes dates only.
    """
    from datetime import date

    from app.config import DATA_DIR

    meta_path = DATA_DIR / "meta.json"
    today = date.today().isoformat()
    try:
        if meta_path.exists():
            import json

            if json.loads(meta_path.read_text()).get("as_of") == today:
                return
        from data.synthetic.generate_sap_data import write as regenerate

        regenerate()
        logger.info("Dataset regenerated for %s", today)
    except Exception as exc:
        logger.warning("Could not refresh the dataset (%s); using what is on disk", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    _ensure_data_is_current()
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
app.include_router(agent_router.router, prefix="/api")


# ---------------------------------------------------------------------------
# Optional single-origin mode.
#
# When a built frontend is present (the Docker image builds it into
# app/static), serve it from this same process. One URL, no CORS, and no
# ordering dependency between deploying the API and building a console that
# needs to know the API's address. Absent the directory this is a no-op and the
# API behaves exactly as before.
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"

if STATIC_DIR.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_console(full_path: str):
        """Serve the console, falling through to index.html for client routes.

        Registered last so every /api route still wins. A request for a real
        file returns that file; anything else returns index.html so the
        single-page app can resolve the route itself.
        """
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")

    logger.info("Serving the console from %s", STATIC_DIR)


@app.get("/api", include_in_schema=False)
def api_root() -> dict:
    return {
        "service": "sap-knowledge-graph",
        "docs": "/docs",
        "endpoints": [
            "GET  /api/health", "GET  /api/suppliers", "POST /api/impact",
            "POST /api/query", "GET  /api/query/examples",
            "POST /api/query/cypher", "POST /api/cypher", "POST /api/agent",
            "GET  /api/graph", "GET  /api/schema", "GET  /api/ontology",
            "GET  /api/validation", "GET  /api/lineage/{node_type}/{node_id}",
            "GET  /api/discovery", "GET  /api/discovery/profile",
        ],
    }
