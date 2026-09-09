"""The AI discovery stage: profiling, inference, and the grounding of both.

The claim under test is that entities and relationships are *derived* rather
than authored. Two things have to hold for that to be true:

  * every relationship SAP declares via a check table must be recovered, and
  * the three relationships whose check table was deliberately withheld must be
    recovered too -- from data overlap alone, and marked ``inferred``.

conftest pins LLM_PROVIDER=none, so everything here exercises the deterministic
path. The committed artifact, produced with an LLM, is validated against the
same rules to prove the two paths agree on structure.
"""

import json

import pytest

from app.config import ARTIFACTS_DIR
from app.discovery import discover as engine
from app.discovery import profile as profiler
from data.synthetic.ddic_catalog import WITHHELD_CHECK_TABLES
from data.synthetic.ddic_catalog import build as build_catalog

# Relationships SAP itself declares. Spot-checked by hand against the catalog.
DECLARED_FOREIGN_KEYS = (
    ("EKKO.LIFNR", "LFA1.LIFNR"),
    ("EKPO.MATNR", "MARA.MATNR"),
    ("EKPO.EBELN", "EKKO.EBELN"),
    ("EKPO.WERKS", "T001W.WERKS"),
    ("EKET.EBELN", "EKKO.EBELN"),
    ("EINA.LIFNR", "LFA1.LIFNR"),
    ("VBAP.VBELN", "VBAK.VBELN"),
    ("VBAK.KUNNR", "KNA1.KUNNR"),
    ("LIPS.VBELN", "LIKP.VBELN"),
    ("RESB.MATNR", "MARA.MATNR"),
    ("AFPO.AUFNR", "AFKO.AUFNR"),
    ("MARD.MATNR", "MARA.MATNR"),
)

WITHHELD_JOINS = tuple(
    (f"{ft}.{ff}", f"{tt}.{tf}") for ft, ff, tt, tf in WITHHELD_CHECK_TABLES
)


@pytest.fixture(scope="module")
def catalog():
    return build_catalog()


@pytest.fixture(scope="module")
def prof():
    return profiler.build_profile()


@pytest.fixture(scope="module")
def ratios(prof):
    return profiler.containment_index(prof)


@pytest.fixture(scope="module")
def discovery():
    """Deterministic discovery, computed in memory so the artifact is untouched."""
    return engine.discover(use_llm=False)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ======================================================================
# The DDIC catalog
# ======================================================================
def test_catalog_covers_every_profiled_column(catalog, prof):
    catalogued = {(r["table"], r["field"]) for r in catalog}
    profiled = {(c["table"], c["field"]) for c in prof["columns"]}
    assert profiled == catalogued, "catalog and data must describe the same columns"


def test_catalog_withholds_exactly_the_intended_check_tables(catalog):
    by_field = {(r["table"], r["field"]): r for r in catalog}
    for from_table, from_field, to_table, _ in WITHHELD_CHECK_TABLES:
        row = by_field[(from_table, from_field)]
        assert row["check_table"] is None, (
            f"{from_table}.{from_field} must carry no check table, or the "
            f"discovery of {to_table} is a lookup rather than an inference"
        )


def test_catalog_still_declares_the_ordinary_foreign_keys(catalog):
    by_field = {(r["table"], r["field"]): r for r in catalog}
    for from_ref, to_ref in DECLARED_FOREIGN_KEYS:
        table, fieldname = from_ref.split(".")
        assert by_field[(table, fieldname)]["check_table"] == to_ref.split(".")[0]


# ======================================================================
# The profiler
# ======================================================================
def test_profile_is_complete(prof):
    assert prof["method"] == "deterministic"
    # Derived, not pinned: the catalogue grows when the dataset does (the BOM
    # tables were added after this test was written), and a hardcoded count
    # fails for a reason that has nothing to do with what is being tested.
    from data.synthetic.ddic_catalog import TABLE_DESCRIPTIONS

    assert len(prof["tables"]) == len(TABLE_DESCRIPTIONS)
    for col in prof["columns"]:
        assert col["rows"] > 0
        assert 0.0 <= col["null_rate"] <= 1.0
        assert 0.0 <= col["cardinality"] <= 1.0
        assert col["distinct"] <= col["non_null"]


def test_profile_identifies_key_columns_as_unique(prof):
    cols = profiler.column_index(prof)
    for ref in ("LFA1.LIFNR", "MARA.MATNR", "T001W.WERKS", "KNA1.KUNNR",
                "EKKO.EBELN", "VBAK.VBELN", "LIKP.VBELN", "AFKO.AUFNR"):
        assert cols[ref]["unique"], f"{ref} should be unique"
    assert not cols["EKPO.EBELN"]["unique"], "an item table repeats its header key"


def test_containment_is_one_for_declared_foreign_keys(ratios):
    for from_ref, to_ref in DECLARED_FOREIGN_KEYS:
        ratio = ratios.get((from_ref, to_ref))
        assert ratio is not None, f"{from_ref} -> {to_ref} missing from the matrix"
        assert ratio >= profiler.FK_THRESHOLD, f"{from_ref} -> {to_ref} = {ratio}"


def test_containment_finds_the_withheld_foreign_keys(ratios):
    """The point of the exercise: no lookup declares these, the data does."""
    for from_ref, to_ref in WITHHELD_JOINS:
        ratio = ratios.get((from_ref, to_ref))
        assert ratio is not None, f"{from_ref} -> {to_ref} missing from the matrix"
        assert ratio >= 0.95, f"{from_ref} -> {to_ref} = {ratio}, too weak to infer"


def test_containment_is_directional(ratios):
    """|A n B| / |A| is not symmetric, and the asymmetry is what picks a parent."""
    assert ratios[("VBAP.VBELN", "VBAK.VBELN")] >= 0.99
    assert ratios.get(("VBAK.VBELN", "LIPS.VGBEL"), 0.0) < 0.95


# ======================================================================
# Discovery
# ======================================================================
def _validate(doc: dict) -> None:
    assert doc["method"] in ("llm", "deterministic")
    assert doc["entities"] and doc["relationships"]
    assert doc["confidence_formula"]["entity"]
    assert doc["confidence_formula"]["relationship"]

    names = {e["name"] for e in doc["entities"]}
    assert len(names) == len(doc["entities"]), "entity names must be unique"

    for e in doc["entities"]:
        assert e["name"] and e["source_table"] and e["business_definition"]
        assert e["key_fields"] and e["evidence"]
        assert 0.0 < e["confidence"] <= 1.0

    seen: set[tuple[str, str]] = set()
    for r in doc["relationships"]:
        assert r["name"] and r["evidence"]
        assert r["cardinality"] in ("1:1", "n:1", "1:n", "n:m")
        assert isinstance(r["inferred"], bool)
        assert 0.0 < r["confidence"] <= 1.0
        assert r["from"] in names and r["to"] in names, (
            f"{r['name']} references an entity that was not discovered"
        )
        join = (r["join"]["from_field"], r["join"]["to_field"])
        assert join not in seen, f"duplicate join {join}"
        seen.add(join)
        for ref in join:
            table, _, fieldname = ref.partition(".")
            assert table and fieldname, f"join field {ref} is not TABLE.FIELD"


def test_discovery_output_matches_the_published_schema(discovery):
    _validate(discovery)
    assert discovery["method"] == "deterministic", "conftest pins LLM_PROVIDER=none"


def test_discovery_recovers_every_declared_foreign_key(discovery):
    found = {(r["join"]["from_field"], r["join"]["to_field"])
             for r in discovery["relationships"]}
    for join in DECLARED_FOREIGN_KEYS:
        assert join in found, f"declared foreign key {join} was not discovered"


def test_withheld_relationships_come_back_inferred(discovery):
    by_join = {(r["join"]["from_field"], r["join"]["to_field"]): r
               for r in discovery["relationships"]}
    for join in WITHHELD_JOINS:
        rel = by_join.get(join)
        assert rel is not None, f"{join} was not recovered from data overlap"
        assert rel["inferred"] is True, (
            f"{join} has no check table, so it must be marked inferred"
        )
        assert any("no check table" in e for e in rel["evidence"])
        assert any("containment 1.00" in e for e in rel["evidence"])


def test_declared_relationships_are_not_marked_inferred(discovery):
    by_join = {(r["join"]["from_field"], r["join"]["to_field"]): r
               for r in discovery["relationships"]}
    for join in DECLARED_FOREIGN_KEYS:
        assert by_join[join]["inferred"] is False
        assert any("check_table" in e for e in by_join[join]["evidence"])


def test_confidence_is_grounded_not_asserted(discovery):
    """An inferred edge must score strictly below a declared one, by the formula."""
    declared = [r for r in discovery["relationships"] if not r["inferred"]]
    inferred = [r for r in discovery["relationships"] if r["inferred"]]
    assert inferred, "the withheld check tables should produce inferred edges"
    assert max(r["confidence"] for r in inferred) < min(
        r["confidence"] for r in declared
    ), "withholding the check table must cost confidence"

    # Every score has to be reproducible from the published formula.
    for r in discovery["relationships"]:
        base = 0.35 + (0.30 if not r["inferred"] else 0.0) + 0.05
        containment = next(
            float(e.split("containment ")[1].split()[0])
            for e in r["evidence"] if e.startswith("containment ")
        )
        assert r["confidence"] == pytest.approx(base + 0.25 * containment, abs=5e-3)


def test_discovery_never_invents_a_join(discovery, ratios, catalog):
    """Every published join is backed by a check table or a measured ratio."""
    declared = {(r["table"], r["field"], r["check_table"]) for r in catalog}
    for r in discovery["relationships"]:
        from_ref, to_ref = r["join"]["from_field"], r["join"]["to_field"]
        from_table, from_field = from_ref.split(".")
        to_table = to_ref.split(".")[0]
        has_check = (from_table, from_field, to_table) in declared
        assert has_check or ratios.get((from_ref, to_ref), 0.0) >= profiler.FK_THRESHOLD


def test_discovery_reports_degraded_sources_honestly(discovery):
    """Whatever is missing has to be named in the output, not quietly skipped."""
    odata = discovery["sources"]["odata"]
    assert odata["available"] == (odata["entity_types"] > 0)
    assert odata["reason"]
    assert len(odata["services"]) == 5
    if not odata["available"]:
        assert any("OData" in n for n in discovery["notes"])

    assert discovery["llm"]["available"] is False, "conftest pins LLM_PROVIDER=none"
    assert any("No LLM naming" in n for n in discovery["notes"])
    assert discovery["sources"]["ddic_catalog"]["declared_check_tables"] > 0
    assert discovery["sources"]["profile"]["foreign_key_threshold"] == profiler.FK_THRESHOLD


def test_committed_artifact_is_valid_and_agrees_on_structure(discovery):
    """The reviewed artifact and a fresh deterministic run must not diverge."""
    path = ARTIFACTS_DIR / "discovery.json"
    if not path.exists():
        pytest.skip("artifacts/discovery.json has not been generated")
    doc = json.loads(path.read_text())
    _validate(doc)

    fresh = {(r["join"]["from_field"], r["join"]["to_field"]): r
             for r in discovery["relationships"]}
    committed = {(r["join"]["from_field"], r["join"]["to_field"]): r
                 for r in doc["relationships"]}
    assert set(fresh) == set(committed), "the two paths must discover the same joins"
    for join, r in committed.items():
        assert r["inferred"] == fresh[join]["inferred"]
        assert r["confidence"] == fresh[join]["confidence"]


# ======================================================================
# SAP OData ingest: degradation
# ======================================================================
def test_metadata_ingest_degrades_without_a_key_or_cache(tmp_path):
    from app.ingest import sapapi

    catalog = sapapi.load_catalog(cache_dir=tmp_path)
    assert catalog.available is False
    assert len(catalog.services) == len(sapapi.SERVICES)
    assert all(s.source == "unavailable" for s in catalog.services)
    assert "README" in catalog.reason
    assert catalog.entity_types == ()
    assert catalog.find_entity_type("Supplier") is None
    assert catalog.navigation_between("PurchaseOrder", "Supplier") is None
    assert catalog.summary()["available"] is False


def test_metadata_ingest_refresh_without_a_key_does_not_raise(tmp_path):
    from app.ingest import sapapi

    meta = sapapi.fetch_metadata("API_BUSINESS_PARTNER", cache_dir=tmp_path, refresh=True)
    assert meta.source == "unavailable"
    assert "SAP_API_KEY" in meta.reason


def test_edmx_parser_reads_keys_and_navigation_properties():
    """Both OData dialects: v4 typed navigation and v2 association roles."""
    from app.ingest import sapapi

    v4 = b"""<?xml version="1.0" encoding="utf-8"?>
    <edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
      <edmx:DataServices>
        <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="NS">
          <EntityType Name="A_Supplier">
            <Key><PropertyRef Name="Supplier"/></Key>
            <Property Name="Supplier" Type="Edm.String" Nullable="false"/>
            <Property Name="SupplierName" Type="Edm.String"/>
            <NavigationProperty Name="to_PurchaseOrder"
                                Type="Collection(NS.A_PurchaseOrder)"/>
          </EntityType>
          <EntityType Name="A_PurchaseOrder">
            <Key><PropertyRef Name="PurchaseOrder"/></Key>
            <Property Name="PurchaseOrder" Type="Edm.String" Nullable="false"/>
          </EntityType>
        </Schema>
      </edmx:DataServices>
    </edmx:Edmx>"""

    types = sapapi.parse_edmx(v4, "API_BUSINESS_PARTNER")
    assert {t.name for t in types} == {"A_Supplier", "A_PurchaseOrder"}
    supplier = next(t for t in types if t.name == "A_Supplier")
    assert supplier.key_properties == ("Supplier",)
    assert [p.name for p in supplier.properties] == ["Supplier", "SupplierName"]
    nav = supplier.navigation_properties[0]
    assert (nav.name, nav.target_entity_type, nav.cardinality) == (
        "to_PurchaseOrder", "A_PurchaseOrder", "n")

    v2 = b"""<?xml version="1.0" encoding="utf-8"?>
    <edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx" Version="1.0">
      <edmx:DataServices>
        <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm" Namespace="NS">
          <EntityType Name="A_Product">
            <Key><PropertyRef Name="Product"/></Key>
            <Property Name="Product" Type="Edm.String" Nullable="false"/>
            <NavigationProperty Name="to_Plant" Relationship="NS.assoc_ProductPlant"
                                FromRole="FromRole_x" ToRole="ToRole_y"/>
          </EntityType>
          <EntityType Name="A_ProductPlant">
            <Key><PropertyRef Name="Plant"/></Key>
            <Property Name="Plant" Type="Edm.String" Nullable="false"/>
          </EntityType>
          <Association Name="assoc_ProductPlant">
            <End Type="NS.A_Product" Multiplicity="1" Role="FromRole_x"/>
            <End Type="NS.A_ProductPlant" Multiplicity="*" Role="ToRole_y"/>
          </Association>
        </Schema>
      </edmx:DataServices>
    </edmx:Edmx>"""

    types = sapapi.parse_edmx(v2, "API_PRODUCT_SRV")
    product = next(t for t in types if t.name == "A_Product")
    nav = product.navigation_properties[0]
    assert (nav.target_entity_type, nav.cardinality) == ("A_ProductPlant", "n")

    assert sapapi.parse_edmx(b"<not xml", "BROKEN") == ()


def test_odata_corroboration_lifts_confidence(tmp_path):
    """A cached NavigationProperty is worth exactly the 0.10 the formula states."""
    from app.ingest import sapapi

    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
      <edmx:DataServices>
        <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="NS">
          <EntityType Name="A_PurchaseOrder">
            <Key><PropertyRef Name="PurchaseOrder"/></Key>
            <Property Name="PurchaseOrder" Type="Edm.String"/>
            <NavigationProperty Name="to_Supplier" Type="NS.A_Supplier"/>
          </EntityType>
          <EntityType Name="A_Supplier">
            <Key><PropertyRef Name="Supplier"/></Key>
            <Property Name="Supplier" Type="Edm.String"/>
          </EntityType>
        </Schema>
      </edmx:DataServices>
    </edmx:Edmx>"""
    (tmp_path / "API_PURCHASEORDER_PROCESS_SRV.xml").write_bytes(xml)

    catalog = sapapi.load_catalog(cache_dir=tmp_path)
    assert catalog.available
    assert catalog.find_entity_type("Supplier").name == "A_Supplier"
    assert catalog.navigation_between("PurchaseOrder", "Supplier") == "to_Supplier"

    cand = engine.JoinCandidate(
        from_table="EKKO", from_field="LIFNR", to_table="LFA1", to_field="LIFNR",
        check_table_declared=True, containment=1.0,
        target_is_key=True, target_unique=True, source_unique=False,
    )
    assert engine.score_relationship(cand, None) == pytest.approx(0.95)
    assert engine.score_relationship(cand, "to_Supplier") == pytest.approx(0.99)


# ======================================================================
# HTTP surface
# ======================================================================
def test_discovery_endpoint_serves_the_document(client):
    d = client.get("/api/discovery").json()
    _validate(d)
    assert d["counts"]["entities"] == len(d["entities"])
    assert d["counts"]["inferred_relationships"] == len(WITHHELD_JOINS)


def test_discovery_profile_endpoint_serves_the_containment_matrix(client):
    p = client.get("/api/discovery/profile").json()
    assert p["counts"]["columns"] > 0
    assert p["thresholds"]["foreign_key"] == profiler.FK_THRESHOLD
    pairs = {(c["from"], c["to"]): c["containment"] for c in p["containment"]}
    for join in WITHHELD_JOINS + DECLARED_FOREIGN_KEYS:
        assert pairs[join] >= profiler.FK_THRESHOLD

    strict = client.get("/api/discovery/profile", params={"min_containment": 1.0}).json()
    assert all(c["containment"] == 1.0 for c in strict["containment"])
    assert strict["counts"]["containment_returned"] <= p["counts"]["containment_returned"]
