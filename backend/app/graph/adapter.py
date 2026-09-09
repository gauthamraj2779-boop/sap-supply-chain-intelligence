"""Graph access abstraction.

Engines call *semantic* methods ("which reservations consume this material at
this plant?"), never raw query strings. That keeps the deterministic engines
identical across a real Neo4j instance and the in-process fallback, and it is
what lets the whole system run and be tested with zero credentials.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class GraphUnavailable(RuntimeError):
    """Raised when the configured backend cannot serve a request."""


class GraphBackend(ABC):
    """Semantic query surface implemented by both backends."""

    name: str = "abstract"

    # -- lifecycle ------------------------------------------------------
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def counts(self) -> dict[str, int]: ...

    # -- master data ----------------------------------------------------
    @abstractmethod
    def supplier(self, lifnr: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def suppliers(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def material(self, matnr: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def plant(self, werks: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def customer(self, kunnr: str) -> dict[str, Any] | None: ...

    # -- procurement ----------------------------------------------------
    @abstractmethod
    def open_schedule_lines_for_supplier(self, lifnr: str) -> list[dict[str, Any]]:
        """EKKO->EKPO->EKET for one supplier: the entry point of the blast radius."""

    @abstractmethod
    def inbound_schedule_lines(
        self, matnr: str, werks: str, exclude_lifnr: str | None = None
    ) -> list[dict[str, Any]]:
        """Other suppliers' incoming quantities for the same material/plant."""

    @abstractmethod
    def alternate_sources(self, matnr: str, exclude_lifnr: str) -> list[dict[str, Any]]:
        """EINA/EINE approved sources other than the delayed supplier."""

    # -- inventory ------------------------------------------------------
    @abstractmethod
    def stock(self, matnr: str, werks: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def stock_all_plants(self, matnr: str) -> list[dict[str, Any]]: ...

    # -- bill of materials ----------------------------------------------
    @abstractmethod
    def bom_for_material(self, matnr: str) -> list[dict[str, Any]]:
        """MAST/STKO/STPO: the direct components of one assembly, one level down."""

    @abstractmethod
    def where_used(self, matnr: str) -> list[dict[str, Any]]:
        """The reverse read: which assemblies consume this material, one level up."""

    # -- production -----------------------------------------------------
    @abstractmethod
    def reservations_for(self, matnr: str, werks: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def production_order(self, aufnr: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def reservations_of_order(self, aufnr: str) -> list[dict[str, Any]]: ...

    # -- demand ---------------------------------------------------------
    @abstractmethod
    def sales_items_for_material(self, matnr: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def deliveries_for_sales_order(self, vbeln: str) -> list[dict[str, Any]]: ...

    # -- visualisation --------------------------------------------------
    @abstractmethod
    def graph_snapshot(self) -> tuple[list[dict], list[dict]]: ...

    # -- escape hatch (Neo4j only) --------------------------------------
    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        raise GraphUnavailable(
            f"Raw Cypher is not supported by the '{self.name}' backend. "
            "Set GRAPH_BACKEND=neo4j with credentials to enable it."
        )

    @property
    def supports_cypher(self) -> bool:
        return False


def build_backend(settings=None) -> GraphBackend:
    """Construct the configured backend, falling back to memory on failure.

    A Neo4j outage degrades to the in-process graph rather than taking the
    whole service down -- the fault-tolerance guarantee.
    """
    from app.config import get_settings

    settings = settings or get_settings()

    if settings.graph_backend == "neo4j":
        if not settings.neo4j_configured:
            logger.warning(
                "GRAPH_BACKEND=neo4j but NEO4J_URI/NEO4J_PASSWORD are unset; "
                "falling back to the in-process memory backend."
            )
        else:
            from app.graph.backends.neo4j_backend import Neo4jBackend

            backend = Neo4jBackend(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
            )
            try:
                backend.connect()
                return backend
            except Exception as exc:
                # Release the half-open driver before falling back, or it lingers
                # until GC and the driver warns about an unclosed session.
                try:
                    backend.close()
                except Exception:
                    pass
                logger.warning(
                    "Neo4j unreachable (%s); falling back to the in-process "
                    "memory backend. Results are identical.", exc
                )

    from app.graph.backends.memory import MemoryBackend

    backend = MemoryBackend()
    backend.connect()
    return backend
