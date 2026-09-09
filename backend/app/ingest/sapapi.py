"""Fetch, cache and parse real SAP OData ``$metadata`` documents.

Why bother: the discovery stage should not have to take a developer's word for
what an SAP entity *is*. SAP publishes that itself. An EDMX document names the
EntityTypes, declares their key properties, and -- the valuable part --
declares ``NavigationProperty`` entries, which are SAP-authored statements that
two entities are related. That is independent corroboration for a relationship
the profiler inferred from data overlap.

Contract, mirroring ``app.engines.llm``: **nothing in this module raises.**
The API key is optional and so is the network. Missing either degrades to the
on-disk cache; a missing cache degrades to an empty catalog that carries the
reason why. Discovery then runs on DDIC + data evidence alone.

Refresh the cache (needs SAP_API_KEY in .env):

    python -m app.ingest.sapapi --refresh
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import ODATA_CACHE_DIR, get_settings

logger = logging.getLogger(__name__)

# lxml parses EDMX faster and is the documented choice, but the stdlib parser
# handles these documents identically and is always present, so the dependency
# stays optional rather than becoming a hard install requirement.
try:  # pragma: no cover - exercised by whichever parser is installed
    from lxml import etree as _etree

    XML_PARSER = "lxml"
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as _etree  # type: ignore[no-redef]

    XML_PARSER = "xml.etree"

# The five services that between them cover the supplier -> customer chain.
SERVICES: tuple[str, ...] = (
    "API_BUSINESS_PARTNER",           # A_Supplier, A_Customer
    "API_PRODUCT_SRV",                # A_Product and its plant/storage views
    "API_PURCHASEORDER_PROCESS_SRV",  # PO header, item, schedule line
    "API_PRODUCTION_ORDER_2_SRV",     # production order + components
    "API_OUTBOUND_DELIVERY_SRV",      # delivery header and item
)


@dataclass(frozen=True)
class ODataProperty:
    name: str
    type: str
    nullable: bool
    label: str | None = None


@dataclass(frozen=True)
class ODataNavigation:
    """A NavigationProperty: SAP's own declaration that two entities relate."""

    name: str
    target_entity_type: str | None
    cardinality: str | None  # "1" | "n"


@dataclass(frozen=True)
class ODataEntityType:
    service: str
    name: str
    key_properties: tuple[str, ...]
    properties: tuple[ODataProperty, ...]
    navigation_properties: tuple[ODataNavigation, ...]


@dataclass(frozen=True)
class ServiceMetadata:
    service: str
    source: str  # "network" | "cache" | "unavailable"
    reason: str
    cache_path: str | None
    entity_types: tuple[ODataEntityType, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.entity_types)


@dataclass(frozen=True)
class MetadataCatalog:
    services: tuple[ServiceMetadata, ...] = ()
    cache_dir: str = ""

    @property
    def available(self) -> bool:
        return any(s.available for s in self.services)

    @property
    def entity_types(self) -> tuple[ODataEntityType, ...]:
        return tuple(et for s in self.services for et in s.entity_types)

    @property
    def reason(self) -> str:
        if self.available:
            got = sum(1 for s in self.services if s.available)
            return f"{len(self.entity_types)} entity types from {got} cached service(s)"
        if not self.services:
            return "no services requested"
        return (
            f"no $metadata cached for {len(self.services)} service(s) in "
            f"{self.cache_dir}; see data/metadata/odata/README.md"
        )

    # -- lookups used for corroborating a discovered relationship --------
    def find_entity_type(self, business_name: str) -> ODataEntityType | None:
        """Match a discovered business name to an SAP EntityType.

        SAP prefixes released API entity types with ``A_`` and writes them in
        singular CamelCase, so ``Supplier`` should find ``A_Supplier``. The
        comparison is on alphanumerics only, with a naive plural strip, because
        the alternative -- a hand-written table name -> entity type map -- is
        exactly the hand-authored provenance this pipeline exists to remove.
        """
        want = _norm(business_name)
        if not want:
            return None
        for et in self.entity_types:
            if _norm(et.name) == want:
                return et
        return None

    def navigation_between(self, from_name: str, to_name: str) -> str | None:
        """Name of a NavigationProperty from one entity type to another."""
        src = self.find_entity_type(from_name)
        dst = self.find_entity_type(to_name)
        if src is None or dst is None:
            return None
        want = _norm(dst.name)
        for nav in src.navigation_properties:
            if nav.target_entity_type and _norm(nav.target_entity_type) == want:
                return nav.name
        return None

    def summary(self, max_properties: int = 25) -> dict:
        """Compact form for the discovery prompt (full EDMX is far too large)."""
        return {
            "available": self.available,
            "reason": self.reason,
            "cache_dir": self.cache_dir,
            "services": [
                {
                    "service": s.service,
                    "source": s.source,
                    "reason": s.reason,
                    "entity_types": [
                        {
                            "entity_type": et.name,
                            "key": list(et.key_properties),
                            "properties": [p.name for p in et.properties[:max_properties]],
                            "navigation_properties": [
                                {"name": n.name, "to": n.target_entity_type,
                                 "cardinality": n.cardinality}
                                for n in et.navigation_properties
                            ],
                        }
                        for et in s.entity_types
                    ],
                }
                for s in self.services
            ],
        }


_ALNUM = re.compile(r"[^a-z0-9]+")
# A_ (released API), C_ (consumption), I_ (interface) are SAP's CDS view
# prefixes; they carry no business meaning and must not defeat a match.
_CDS_PREFIX = re.compile(r"^[ACIE]_")


def _norm(name: str) -> str:
    n = _ALNUM.sub("", _CDS_PREFIX.sub("", name).casefold())
    return n[:-1] if n.endswith("s") and len(n) > 3 else n


# ======================================================================
# EDMX parsing
# ======================================================================
def _local(tag: object) -> str:
    """Tag name without its namespace.

    EDMX ships under at least four namespaces across OData v2 CSDL revisions
    and v4, and SAP serves a mix. Matching on local names sidesteps all of it.
    """
    t = str(tag)
    return t.rsplit("}", 1)[-1]


def _iter(node) -> list:
    # lxml also yields comments and processing instructions, whose .tag is a
    # callable rather than a string; skip them.
    return [n for n in node.iter() if isinstance(getattr(n, "tag", None), str)]


def _sap_label(elem) -> str | None:
    for key, value in elem.attrib.items():
        if _local(key) == "label":
            return value
    return None


def _strip_type(raw: str | None) -> tuple[str | None, str | None]:
    """``Collection(NS.A_PurchaseOrderItem)`` -> (``A_PurchaseOrderItem``, ``n``)."""
    if not raw:
        return None, None
    card = "1"
    inner = raw.strip()
    if inner.startswith("Collection(") and inner.endswith(")"):
        inner, card = inner[len("Collection("):-1], "n"
    return inner.rsplit(".", 1)[-1], card


def parse_edmx(xml: bytes, service: str) -> tuple[ODataEntityType, ...]:
    """Parse an EDMX document into entity types. Returns () on malformed input."""
    try:
        root = _etree.fromstring(xml)
    except Exception as exc:
        logger.warning("EDMX parse failed for %s: %s", service, exc)
        return ()

    # OData v2 puts the navigation target in a separate <Association>; v4 puts
    # it on the NavigationProperty itself. Index the v2 form first.
    associations: dict[str, list[tuple[str, str]]] = {}
    for elem in _iter(root):
        if _local(elem.tag) != "Association":
            continue
        ends = []
        for end in elem:
            if _local(end.tag) != "End":
                continue
            etype, _ = _strip_type(end.get("Type"))
            role = end.get("Role") or ""
            mult = end.get("Multiplicity") or ""
            ends.append((role, etype or "", "n" if mult == "*" else "1"))
        if ends:
            associations[elem.get("Name") or ""] = [(r, f"{t}|{m}") for r, t, m in ends]

    out: list[ODataEntityType] = []
    for elem in _iter(root):
        if _local(elem.tag) != "EntityType":
            continue
        name = elem.get("Name")
        if not name:
            continue

        keys: list[str] = []
        props: list[ODataProperty] = []
        navs: list[ODataNavigation] = []
        for child in elem:
            kind = _local(child.tag)
            if kind == "Key":
                keys += [r.get("Name") for r in child if r.get("Name")]
            elif kind == "Property":
                props.append(ODataProperty(
                    name=child.get("Name") or "",
                    type=child.get("Type") or "",
                    nullable=(child.get("Nullable", "true").lower() != "false"),
                    label=_sap_label(child),
                ))
            elif kind == "NavigationProperty":
                target, card = _strip_type(child.get("Type"))
                if target is None:
                    # v2: resolve through the association's ToRole end.
                    rel = (child.get("Relationship") or "").rsplit(".", 1)[-1]
                    to_role = child.get("ToRole") or ""
                    for role, packed in associations.get(rel, []):
                        if role == to_role:
                            target, card = packed.split("|", 1)
                            break
                navs.append(ODataNavigation(
                    name=child.get("Name") or "",
                    target_entity_type=target or None,
                    cardinality=card,
                ))

        out.append(ODataEntityType(
            service=service, name=name, key_properties=tuple(keys),
            properties=tuple(props), navigation_properties=tuple(navs),
        ))
    return tuple(out)


# ======================================================================
# Fetch + cache
# ======================================================================
def cache_path_for(service: str, cache_dir: Path | None = None) -> Path:
    return (cache_dir or ODATA_CACHE_DIR) / f"{service}.xml"


def fetch_metadata(
    service: str,
    *,
    settings=None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    timeout: float = 20.0,
) -> ServiceMetadata:
    """One service's ``$metadata``, from the network if allowed, else the cache.

    ``refresh`` is opt-in: the default path never touches the network, so a
    demo cannot be broken by SAP rate limits or an expired sandbox key.
    """
    settings = settings or get_settings()
    path = cache_path_for(service, cache_dir)
    key = settings.sap_api_key

    if refresh:
        if not key:
            reason = "SAP_API_KEY is not set; refresh skipped"
        else:
            url = f"{settings.sap_sandbox_base_url.rstrip('/')}/{service}/$metadata"
            try:
                import httpx

                r = httpx.get(url, headers={"apikey": key, "Accept": "application/xml"},
                              timeout=timeout, follow_redirects=True)
                r.raise_for_status()
                body = r.content
                types = parse_edmx(body, service)
                if types:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                    return ServiceMetadata(service, "network", f"fetched {len(body)} bytes",
                                           str(path), types)
                reason = f"fetched {len(body)} bytes but no EntityType was parsed"
            except Exception as exc:
                reason = f"fetch failed ({type(exc).__name__}: {exc})"
            logger.warning("SAP metadata refresh for %s: %s", service, reason)
    else:
        reason = "offline (no refresh requested)"

    if path.exists():
        types = parse_edmx(path.read_bytes(), service)
        if types:
            return ServiceMetadata(service, "cache", f"read from {path.name}",
                                   str(path), types)
        return ServiceMetadata(service, "unavailable",
                               f"cached {path.name} contained no EntityType", str(path))

    return ServiceMetadata(
        service, "unavailable",
        f"no cached {path.name} and none fetched ({reason})", None,
    )


def load_catalog(
    services: tuple[str, ...] = SERVICES,
    *,
    settings=None,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> MetadataCatalog:
    """All five services. Always returns a catalog, never raises."""
    directory = cache_dir or ODATA_CACHE_DIR
    out: list[ServiceMetadata] = []
    for service in services:
        try:
            out.append(fetch_metadata(service, settings=settings,
                                      cache_dir=directory, refresh=refresh))
        except Exception as exc:  # defence in depth: the caller must not care
            logger.warning("SAP metadata load for %s failed: %s", service, exc)
            out.append(ServiceMetadata(service, "unavailable",
                                       f"unexpected error: {exc}", None))
    return MetadataCatalog(tuple(out), str(directory))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Refresh the SAP OData $metadata cache.")
    ap.add_argument("--refresh", action="store_true",
                    help="call SAP (needs SAP_API_KEY); otherwise read the cache only")
    args = ap.parse_args(argv)

    catalog = load_catalog(refresh=args.refresh)
    print(f"parser={XML_PARSER}  cache={catalog.cache_dir}")
    for s in catalog.services:
        print(f"  {s.service:<32} {s.source:<12} {len(s.entity_types):>3} types  {s.reason}")
    print(f"  {'':<32} {'TOTAL':<12} {len(catalog.entity_types):>3} types")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
