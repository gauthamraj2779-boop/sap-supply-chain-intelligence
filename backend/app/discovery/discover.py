"""Discover business entities and relationships from SAP metadata and data.

This replaces "a developer wrote it down" with "the pipeline worked it out",
from three independent sources:

  1. a DDIC catalog (key flags, data elements, domains, check tables),
  2. real SAP OData ``$metadata`` when the cache holds it (EntityType names and
     NavigationProperty declarations),
  3. a deterministic profile of the data itself (containment ratios).

The division of labour matters. **Structure is never the model's opinion.**
Which joins exist, whether each was declared or inferred, and how confident to
be are all computed here from (1) and (3); a relationship the evidence does not
support is discarded even if the model asserts it, and one the evidence does
support is added even if the model missed it. What the model contributes is
what it is actually good at: reading ``LFA1`` / "Vendor Master (General
Section)" and calling it a Supplier, folding EKKO and EKPO into one
PurchaseOrder, and naming the edge ``orderedFrom``.

With no LLM configured the same structure comes out named after its SAP tables
and marked ``method: "deterministic"``. Nothing about the discovery is lost --
only the business vocabulary is.

Run:  python -m app.discovery.discover
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import ARTIFACTS_DIR
from app.discovery import profile as profiler
from app.ingest import sapapi

logger = logging.getLogger(__name__)

ENTITY_CONFIDENCE_FORMULA = (
    "0.40 base (table profiled and catalogued) "
    "+ 0.30 DDIC declares a key + 0.20 that key is unique across the rows "
    "+ 0.10 a matching OData EntityType exists; capped at 0.99"
)
RELATIONSHIP_CONFIDENCE_FORMULA = (
    "0.35 base (a profiled join candidate at all) "
    "+ 0.30 DDIC check table declares it + 0.25 x containment ratio "
    "+ 0.05 the target field is a declared key "
    "+ 0.10 a corroborating OData NavigationProperty; capped at 0.99"
)

# Structure the LLM is asked for. It supplies naming and business meaning only;
# every structural field in the output is recomputed from evidence afterwards.
DISCOVERY_SCHEMA: dict = {
    "type": "object",
    "required": ["entities", "relationships"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "source_table", "business_definition"],
                "properties": {
                    "name": {"type": "string"},
                    "source_table": {"type": "string"},
                    "also_covers_tables": {"type": "array", "items": {"type": "string"}},
                    "business_definition": {"type": "string"},
                },
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "from", "to", "join"],
                "properties": {
                    "name": {"type": "string"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "business_meaning": {"type": "string"},
                    "join": {
                        "type": "object",
                        "required": ["from_field", "to_field"],
                        "properties": {
                            "from_field": {"type": "string"},
                            "to_field": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


# ======================================================================
# Deterministic evidence
# ======================================================================
@dataclass
class JoinCandidate:
    from_table: str
    from_field: str
    to_table: str
    to_field: str
    check_table_declared: bool
    containment: float
    target_is_key: bool
    target_unique: bool
    source_unique: bool
    composite_key_member: bool = False

    @property
    def from_ref(self) -> str:
        return f"{self.from_table}.{self.from_field}"

    @property
    def to_ref(self) -> str:
        return f"{self.to_table}.{self.to_field}"

    @property
    def inferred(self) -> bool:
        """No check table names this join: it exists only because the data says so."""
        return not self.check_table_declared

    @property
    def cardinality(self) -> str:
        return "1:1" if self.source_unique else "n:1"


@dataclass
class EntityCandidate:
    table: str
    table_desc: str
    key_fields: list[str]
    rows: int
    key_is_unique: bool
    fields: list[str] = field(default_factory=list)


def _resolve_target_field(check_table: str, source: dict, by_table: dict[str, list[dict]]) -> str | None:
    """Which field of the check table the reference lands on.

    DDIC records the table, not the column, so it is recovered in the order a
    human would: same data element, same name, same domain, then -- only if the
    check table has a single key -- that key.
    """
    target_keys = [r for r in by_table.get(check_table, []) if r["key_flag"]]
    if not target_keys:
        return None
    for attr in ("data_element", "field", "domain"):
        want = source.get(attr)
        if not want:
            continue
        for r in target_keys:
            if r.get(attr) == want:
                return r["field"]
    return target_keys[0]["field"] if len(target_keys) == 1 else None


def build_candidates(catalog: list[dict], prof: dict) -> list[JoinCandidate]:
    """Every join the evidence supports, declared or inferred."""
    by_table: dict[str, list[dict]] = {}
    for r in catalog:
        by_table.setdefault(r["table"], []).append(r)
    by_field = {(r["table"], r["field"]): r for r in catalog}
    cols = profiler.column_index(prof)
    ratios = profiler.containment_index(prof)

    def stats(ref: str) -> dict:
        return cols.get(ref, {})

    out: dict[tuple[str, str], JoinCandidate] = {}

    # -- 1. declared: DDIC check tables, SAP's own foreign keys ----------
    for row in catalog:
        check = row.get("check_table")
        # A check table outside this catalog (T005, TCURC, ...) is real but out
        # of scope; there is nothing to join to, so it is skipped rather than
        # guessed at.
        if not check or check not in by_table:
            continue
        to_field = _resolve_target_field(check, row, by_table)
        if not to_field:
            continue
        src, dst = f"{row['table']}.{row['field']}", f"{check}.{to_field}"
        target = by_field.get((check, to_field), {})
        out[(src, dst)] = JoinCandidate(
            from_table=row["table"], from_field=row["field"],
            to_table=check, to_field=to_field,
            check_table_declared=True,
            containment=ratios.get((src, dst), 0.0),
            target_is_key=bool(target.get("key_flag")),
            target_unique=bool(stats(dst).get("unique")),
            source_unique=bool(stats(src).get("unique")),
            composite_key_member=sum(
                1 for r in by_table.get(check, []) if r["key_flag"]) > 1,
        )

    # -- 2. inferred: containment alone ----------------------------------
    # A join target has to identify a row, so it must be a declared key that is
    # actually unique in the data. And a target that is itself a foreign key is
    # a waypoint, not a home: RESB.AUFNR contains into both AFPO.AUFNR and
    # AFKO.AUFNR, and only AFKO owns the order number.
    declared_pairs = set(out)
    for (src, dst), ratio in ratios.items():
        if ratio < profiler.FK_THRESHOLD or (src, dst) in declared_pairs:
            continue
        from_table, from_field = src.split(".", 1)
        to_table, to_field = dst.split(".", 1)
        target = by_field.get((to_table, to_field))
        source = by_field.get((from_table, from_field))
        if not target or not source:
            continue
        if not target["key_flag"] or not stats(dst).get("unique"):
            continue
        if target.get("check_table"):
            continue
        if (dst, src) in declared_pairs:  # the declared direction wins
            continue
        out[(src, dst)] = JoinCandidate(
            from_table=from_table, from_field=from_field,
            to_table=to_table, to_field=to_field,
            check_table_declared=False,
            containment=ratio,
            target_is_key=True,
            target_unique=True,
            source_unique=bool(stats(src).get("unique")),
            composite_key_member=sum(
                1 for r in by_table.get(to_table, []) if r["key_flag"]) > 1,
        )

    return sorted(out.values(), key=lambda c: (c.from_table, c.from_field, c.to_table))


def build_entity_candidates(catalog: list[dict], prof: dict) -> list[EntityCandidate]:
    tables: dict[str, list[dict]] = {}
    for r in catalog:
        tables.setdefault(r["table"], []).append(r)
    rows_by_table = {t["table"]: t["rows"] for t in prof.get("tables", [])}

    data = profiler.load_tables()
    out: list[EntityCandidate] = []
    for table, fields in tables.items():
        if table not in rows_by_table:
            continue
        keys = [r["field"] for r in fields if r["key_flag"]]
        records = data.get(table, [])
        # Verify the declared key in the data instead of trusting the flag: a
        # composite key that repeats is not a key.
        seen = {tuple(str(r.get(k)) for k in keys) for r in records} if keys else set()
        out.append(EntityCandidate(
            table=table,
            table_desc=fields[0]["table_desc"],
            key_fields=keys,
            rows=rows_by_table[table],
            key_is_unique=bool(keys and records and len(seen) == len(records)),
            fields=[r["field"] for r in fields],
        ))
    return sorted(out, key=lambda e: e.table)


# ======================================================================
# Grounded confidence
# ======================================================================
def score_relationship(cand: JoinCandidate, odata_nav: str | None) -> float:
    score = 0.35
    score += 0.30 if cand.check_table_declared else 0.0
    score += 0.25 * min(cand.containment, 1.0)
    score += 0.05 if cand.target_is_key else 0.0
    score += 0.10 if odata_nav else 0.0
    return round(min(score, 0.99), 4)


def score_entity(cand: EntityCandidate, odata_type: str | None) -> float:
    score = 0.40
    score += 0.30 if cand.key_fields else 0.0
    score += 0.20 if cand.key_is_unique else 0.0
    score += 0.10 if odata_type else 0.0
    return round(min(score, 0.99), 4)


def relationship_evidence(cand: JoinCandidate, odata_nav: str | None) -> list[str]:
    ev: list[str] = []
    if cand.check_table_declared:
        ev.append(f"DDIC check_table={cand.to_table} on {cand.from_ref}")
    else:
        ev.append(
            f"no check table declares {cand.from_ref}; inferred from data overlap alone"
        )
    ev.append(f"containment {cand.containment:.2f} of {cand.from_ref} into {cand.to_ref}")
    if cand.target_is_key:
        ev.append(f"DD03L key flag on {cand.to_ref}")
    if cand.target_unique:
        ev.append(f"{cand.to_ref} is unique across its rows")
    if cand.composite_key_member:
        ev.append(f"{cand.to_ref} is one field of a composite key; join on the full key")
    ev.append(
        f"cardinality {cand.cardinality} observed: {cand.from_ref} is "
        f"{'unique' if cand.source_unique else 'repeated'} in this extract"
    )
    if odata_nav:
        ev.append(f"OData NavigationProperty {odata_nav}")
    return ev


def entity_evidence(cand: EntityCandidate, odata_type: str | None) -> list[str]:
    ev = [f"DD02T table text '{cand.table_desc}'", f"{cand.rows} rows profiled"]
    if cand.key_fields:
        ev.append(f"DD03L key flag on {', '.join(cand.key_fields)}")
    if cand.key_is_unique:
        ev.append(f"declared key is unique across all {cand.rows} rows")
    if odata_type:
        ev.append(f"OData EntityType {odata_type}")
    return ev


# ======================================================================
# Naming (the part the LLM improves on)
# ======================================================================
_NON_WORD = re.compile(r"[^0-9A-Za-z]+")


def _camel(text: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in _NON_WORD.split(text) if p)


def _lower_camel(text: str) -> str:
    """``PurchaseOrder`` -> ``purchaseOrder``; ``MARC`` -> ``marc``, not ``mARC``."""
    c = _camel(text)
    return c.lower() if c.isupper() else c[:1].lower() + c[1:]


def _derived_relationship_name(
    from_entity: str, to_entity: str, from_field: str, taken: set[str]
) -> str:
    """Fallback name when no model named the edge. Must be unique per document.

    ``(from table, from field, to table)`` is unique by construction, so the
    third form always terminates.
    """
    lower = _lower_camel(from_entity)
    if from_entity == to_entity:
        # A join the model folded inside one entity: an item line pointing at
        # its own header. "hasPurchaseOrder" would read as an edge to something
        # else, which it is not.
        forms = (f"partOf{_camel(to_entity)}",
                 f"partOf{_camel(to_entity)}Via{_camel(from_field)}")
    else:
        forms = (f"has{_camel(to_entity)}",
                 f"{lower}Has{_camel(to_entity)}",
                 f"{lower}Has{_camel(to_entity)}Via{_camel(from_field)}")
    for name in forms:
        if name not in taken:
            return name
    return f"{lower}_{_camel(from_field)}_{_camel(to_entity)}"


# ======================================================================
# Assembly
# ======================================================================
def _assemble(
    entity_cands: list[EntityCandidate],
    join_cands: list[JoinCandidate],
    odata: sapapi.MetadataCatalog,
    naming: dict | None,
) -> tuple[list[dict], list[dict], list[str]]:
    """Merge deterministic structure with (optional) model-supplied naming."""
    notes: list[str] = []

    by_table = {c.table: c for c in entity_cands}

    # table -> (entity name, definition, is this the entity's primary table)
    named: dict[str, tuple[str, str, bool]] = {}
    if naming:
        for e in naming.get("entities", []):
            name = str(e.get("name") or "").strip()
            primary = str(e.get("source_table") or "").strip().upper()
            definition = str(e.get("business_definition") or "").strip()
            if not name or primary not in by_table:
                continue
            named.setdefault(primary, (name, definition, True))
            for extra in e.get("also_covers_tables", []):
                table = str(extra).strip().upper()
                if table in by_table:
                    named.setdefault(table, (name, definition, False))

    entity_name = {t: (named[t][0] if t in named else t) for t in by_table}

    # -- entities, one per business name ---------------------------------
    # A header and its items are one business object, so the entity is keyed on
    # the table the model nominated as primary; the others are recorded as
    # spanned tables rather than folded into the key.
    grouped: dict[str, list[EntityCandidate]] = {}
    for cand in entity_cands:
        grouped.setdefault(entity_name[cand.table], []).append(cand)

    entities: list[dict] = []
    for name, members in grouped.items():
        primary = next(
            (m for m in members if named.get(m.table, ("", "", False))[2]), members[0]
        )
        odata_type = odata.find_entity_type(name)
        odata_name = odata_type.name if odata_type else None
        definition = named.get(primary.table, ("", "", False))[1] or primary.table_desc
        evidence = entity_evidence(primary, odata_name)
        for other in members:
            if other is not primary:
                evidence.append(f"also spans {other.table} ({other.table_desc}), "
                                f"key {', '.join(other.key_fields)}")
        entities.append({
            "name": name,
            "source_table": primary.table,
            "key_fields": list(primary.key_fields),
            "business_definition": definition,
            "confidence": score_entity(primary, odata_name),
            "evidence": evidence,
        })
    entities.sort(key=lambda e: e["name"])

    # -- relationships ---------------------------------------------------
    supplied: dict[tuple[str, str], dict] = {}
    if naming:
        for r in naming.get("relationships", []):
            join = r.get("join") or {}
            key = (str(join.get("from_field", "")).upper().strip(),
                   str(join.get("to_field", "")).upper().strip())
            if key[0] and key[1]:
                supplied.setdefault(key, r)

    relationships: list[dict] = []
    taken: set[str] = set()
    for cand in join_cands:
        src_entity = entity_name.get(cand.from_table, cand.from_table)
        dst_entity = entity_name.get(cand.to_table, cand.to_table)
        nav = odata.navigation_between(src_entity, dst_entity)
        proposed = supplied.pop((cand.from_ref, cand.to_ref), None)

        name = str((proposed or {}).get("name") or "").strip()
        if not name or name in taken:
            name = _derived_relationship_name(
                src_entity, dst_entity, cand.from_field, taken)
        taken.add(name)

        row = {
            "name": name,
            "from": src_entity,
            "to": dst_entity,
            "cardinality": cand.cardinality,
            "join": {"from_field": cand.from_ref, "to_field": cand.to_ref},
            "confidence": score_relationship(cand, nav),
            "inferred": cand.inferred,
            "evidence": relationship_evidence(cand, nav),
        }
        if src_entity == dst_entity:
            row["evidence"].append(
                f"{cand.from_table} and {cand.to_table} were folded into one "
                f"{src_entity} entity, so this is its internal header/item join"
            )
        meaning = str((proposed or {}).get("business_meaning") or "").strip()
        if meaning:
            row["business_meaning"] = meaning
        relationships.append(row)

    if supplied:
        # Anything the model proposed that no check table and no containment
        # ratio backs is dropped rather than published. Reported, not hidden.
        notes.append(
            f"{len(supplied)} model-proposed relationship(s) were discarded for lack "
            f"of deterministic evidence: "
            + ", ".join(sorted(f"{a}->{b}" for a, b in supplied))
        )

    inferred = sum(1 for r in relationships if r["inferred"])
    if inferred:
        notes.append(
            f"{inferred} of {len(relationships)} relationships carry inferred=true: no "
            "check table declares them, so they were recovered from data containment "
            "alone and scored lower accordingly."
        )
    return entities, relationships, notes


# ======================================================================
# The LLM call
# ======================================================================
_SYSTEM = (
    "You are a data architect reverse-engineering an SAP ERP extract into a "
    "business knowledge graph. You are given a DDIC field catalog, a summary of "
    "SAP OData $metadata, and a deterministic data profile with containment "
    "ratios between columns.\n\n"
    "Your job is NAMING and BUSINESS MEANING, not structure. For every table, "
    "give the business entity it represents, using S/4HANA vocabulary (LFA1 is a "
    "Supplier, KNA1 a Customer, MARA a Material, T001W a Plant). Where a header "
    "table and its item table describe one business object, name the entity once "
    "on the header and list the item table in also_covers_tables. For every join "
    "you can support from the evidence, give the relationship a short lowerCamel "
    "business name (orderedFrom, suppliedBy, fulfils, stockedAt) and one sentence "
    "of meaning.\n\n"
    "Rules. Copy each join.from_field / join.to_field VERBATIM from one entry of "
    "containment_candidates, or from a ddic_fields row with a check_table (the "
    "field itself as from_field, the check table's key as to_field). Never build "
    "a pair from two columns of the same table - that is not a join, and any "
    "relationship the evidence does not back is discarded. Cover every candidate "
    "you can justify, including the ones with no check_table. Do not invent "
    "confidence numbers or cardinalities; both are computed from the evidence."
)


def _prompt_payload(
    catalog: list[dict], prof: dict, odata: sapapi.MetadataCatalog
) -> str:
    cols = profiler.column_index(prof)
    ddic = [
        {"t": r["table"], "f": r["field"], "k": r["key_flag"],
         "de": r["data_element"], "dom": r["domain"],
         "txt": r["field_desc"], "check": r["check_table"]}
        for r in catalog
    ]
    # Only joins whose target identifies a row are worth showing; a value that
    # repeats in the target table cannot be a foreign key destination.
    joins, omitted = [], 0
    for p in prof.get("containment", []):
        if p["containment"] < profiler.FK_THRESHOLD:
            omitted += 1
            continue
        if not cols.get(p["to"], {}).get("unique"):
            omitted += 1
            continue
        joins.append({"from": p["from"], "to": p["to"], "containment": p["containment"]})

    payload = {
        "tables": [{"table": t["table"], "rows": t["rows"],
                    "desc": next((r["table_desc"] for r in catalog
                                  if r["table"] == t["table"]), "")}
                   for t in prof.get("tables", [])],
        "ddic_fields": ddic,
        "column_profile": [
            {"col": f"{c['table']}.{c['field']}", "kind": c["kind"],
             "distinct": c["distinct"], "null_rate": c["null_rate"],
             "unique": c["unique"]}
            for c in prof.get("columns", [])
        ],
        "containment_candidates": joins,
        "containment_omitted": omitted,
        "odata_metadata": odata.summary(),
    }
    return json.dumps(payload, separators=(",", ":"))


def request_naming(
    catalog: list[dict], prof: dict, odata: sapapi.MetadataCatalog
) -> dict | None:
    from app.engines.llm import get_llm

    llm = get_llm()
    if not llm.available:
        return None
    return llm.complete_json(
        _SYSTEM, _prompt_payload(catalog, prof, odata), DISCOVERY_SCHEMA,
        max_tokens=8000,
    )


# ======================================================================
# Entry points
# ======================================================================
def discover(*, use_llm: bool = True, refresh_metadata: bool = False) -> dict:
    """Run the pipeline and return the discovery document. Never raises."""
    from data.synthetic.ddic_catalog import load as load_catalog

    catalog = load_catalog()
    prof = profiler.build_profile()
    odata = sapapi.load_catalog(refresh=refresh_metadata)

    entity_cands = build_entity_candidates(catalog, prof)
    join_cands = build_candidates(catalog, prof)

    naming = request_naming(catalog, prof, odata) if use_llm else None
    entities, relationships, notes = _assemble(entity_cands, join_cands, odata, naming)

    from app.engines.llm import get_llm

    st = get_llm().status()
    if naming is None:
        notes.insert(0, (
            "No LLM naming: entities are named after their SAP tables and defined by "
            "their DD02T text. Structure, evidence and confidence are identical to "
            "the LLM path -- only the business vocabulary is absent."
        ))
    if not odata.available:
        notes.append(
            f"OData $metadata unavailable ({odata.reason}). No NavigationProperty "
            "corroboration was applied, so every confidence below is the 0.10 "
            "OData term short of its ceiling."
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "llm" if naming else "deterministic",
        "llm": {"provider": st.provider, "model": st.model,
                "available": st.available, "detail": st.reason},
        "sources": {
            "ddic_catalog": {
                "fields": len(catalog),
                "tables": len({r["table"] for r in catalog}),
                "declared_check_tables": sum(1 for r in catalog if r["check_table"]),
            },
            "profile": {
                "columns": len(prof.get("columns", [])),
                "containment_pairs": len(prof.get("containment", [])),
                "foreign_key_threshold": profiler.FK_THRESHOLD,
            },
            "odata": {
                "available": odata.available,
                "reason": odata.reason,
                "entity_types": len(odata.entity_types),
                "services": [{"service": s.service, "source": s.source,
                              "entity_types": len(s.entity_types)}
                             for s in odata.services],
            },
        },
        "confidence_formula": {
            "entity": ENTITY_CONFIDENCE_FORMULA,
            "relationship": RELATIONSHIP_CONFIDENCE_FORMULA,
            "note": (
                "Confidence is computed from the deterministic evidence listed on each "
                "record. It is never the model's self-report, and it is identical "
                "whether or not an LLM ran."
            ),
        },
        "entities": entities,
        "relationships": relationships,
        "notes": notes,
    }


def write(path: Path | None = None, **kwargs) -> Path:
    out = path or (ARTIFACTS_DIR / "discovery.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(discover(**kwargs), indent=2))
    return out


def load(path: Path | None = None) -> dict:
    """The committed discovery document, recomputed in memory if it is absent.

    A GET must not write to the repository, so the fallback stays in memory and
    skips the LLM: an API request is not the place to spend a token budget.
    """
    src = path or (ARTIFACTS_DIR / "discovery.json")
    if src.exists():
        try:
            return json.loads(src.read_text())
        except Exception as exc:
            logger.warning("discovery.json unreadable (%s); recomputing", exc)
    return discover(use_llm=False)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Discover entities and relationships.")
    ap.add_argument("--no-llm", action="store_true", help="force the deterministic path")
    ap.add_argument("--refresh-metadata", action="store_true",
                    help="re-fetch SAP $metadata first (needs SAP_API_KEY)")
    args = ap.parse_args(argv)

    doc = discover(use_llm=not args.no_llm, refresh_metadata=args.refresh_metadata)
    out = ARTIFACTS_DIR / "discovery.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))

    inferred = [r for r in doc["relationships"] if r["inferred"]]
    print(f"  method={doc['method']}  ({doc['llm']['provider']}/{doc['llm']['model']})")
    print(f"  {len(doc['entities'])} entities, {len(doc['relationships'])} relationships, "
          f"{len(inferred)} inferred")
    for r in inferred:
        print(f"    inferred  {r['join']['from_field']:<14} -> {r['join']['to_field']:<14} "
              f"conf {r['confidence']}  ({r['from']} -{r['name']}-> {r['to']})")
    for n in doc["notes"]:
        print(f"  note: {n}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
