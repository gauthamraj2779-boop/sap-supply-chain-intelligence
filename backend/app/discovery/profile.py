"""Deterministic data profiling. No LLM, no network, no randomness.

Two products, both reproducible byte-for-byte:

*column statistics* -- cardinality, null rate, min/max and samples per column.

*containment* -- for every compatible ordered column pair ``(A, B)`` drawn from
different tables, the ratio ``|distinct(A) & distinct(B)| / |distinct(A)|``.
A ratio of 1.0 means every value in A already exists in B, which is precisely
what a foreign key looks like from the data side. At >= 0.95 into a column that
is both a declared key and unique in practice, it is strong evidence -- and it
is evidence the discovery stage cannot fake, because it is measured here before
any model is asked anything.

Run:  python -m app.discovery.profile
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.config import ARTIFACTS_DIR, DATA_DIR

# Containment at or above this into a unique key column is treated as a
# foreign key. 0.95 rather than 1.0 leaves room for the handful of orphan rows
# every real extract carries.
FK_THRESHOLD = 0.95
# Everything at or above this is published in the matrix, so a reviewer can see
# the near misses that were rejected as well as the hits that were accepted.
REPORT_THRESHOLD = 0.50
# Single-value columns match almost anything by accident; a column has to carry
# at least this much variety before its containment counts as evidence.
MIN_DISTINCT = 2

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ANNOTATION_PREFIX = "_"  # _assumption, _role: authoring notes, not data


def dataset_map() -> dict[str, str]:
    """SAP table -> generated JSON file stem.

    Built by inverting the generator's own TABLE_MAP so the two can never
    disagree. ``EINA/EINE`` names two tables in one extract; it is keyed on the
    general-data table, which is where its key fields live.
    """
    from data.synthetic.generate_sap_data import TABLE_MAP

    return {sap.split("/")[0]: dataset for dataset, sap in TABLE_MAP.items()}


def load_tables(data_dir: Path | None = None) -> dict[str, list[dict]]:
    """Every generated table, keyed by SAP table name. Missing files are skipped."""
    directory = data_dir or DATA_DIR
    out: dict[str, list[dict]] = {}
    for table, dataset in dataset_map().items():
        path = directory / f"{dataset}.json"
        if not path.exists():
            continue
        try:
            rows = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(rows, list):
            out[table] = rows
    return out


# ======================================================================
# Column statistics
# ======================================================================
def _kind(values: list) -> str:
    if not values:
        return "empty"
    if all(isinstance(v, bool) for v in values):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "numeric"
    if all(isinstance(v, str) and _DATE.match(v) for v in values):
        return "date"
    return "text"


def _canonical(value, kind: str) -> str:
    """A comparable form, so 850 and 850.0 are the same key in one numeric column."""
    if kind == "numeric":
        return repr(float(value))
    return str(value)


def profile_column(table: str, fieldname: str, rows: list[dict]) -> dict:
    raw = [r.get(fieldname) for r in rows]
    present = [v for v in raw if v is not None and v != ""]
    kind = _kind(present)
    distinct = sorted({_canonical(v, kind) for v in present})

    if kind == "numeric" and present:
        lo, hi = min(float(v) for v in present), max(float(v) for v in present)
    elif present:
        lo, hi = min(str(v) for v in present), max(str(v) for v in present)
    else:
        lo = hi = None

    n = len(rows)
    return {
        "table": table,
        "field": fieldname,
        "kind": kind,
        "rows": n,
        "non_null": len(present),
        "null_rate": round(1.0 - (len(present) / n), 4) if n else 1.0,
        "distinct": len(distinct),
        # Cardinality as the standard ratio: 1.0 means every row has its own value.
        "cardinality": round(len(distinct) / len(present), 4) if present else 0.0,
        "unique": bool(present) and len(distinct) == len(present) == n,
        "min": lo,
        "max": hi,
        "samples": distinct[:5],
    }


def _columns_of(rows: list[dict]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        for k in r:
            if not k.startswith(_ANNOTATION_PREFIX) and k not in seen:
                seen.append(k)
    return seen


# ======================================================================
# Containment
# ======================================================================
def containment(tables: dict[str, list[dict]]) -> tuple[list[dict], dict[str, set[str]]]:
    """Ordered containment ratios for every compatible cross-table column pair."""
    values: dict[str, set[str]] = {}
    kinds: dict[str, str] = {}
    for table, rows in tables.items():
        for fieldname in _columns_of(rows):
            present = [r[fieldname] for r in rows
                       if r.get(fieldname) is not None and r.get(fieldname) != ""]
            kind = _kind(present)
            values[f"{table}.{fieldname}"] = {_canonical(v, kind) for v in present}
            kinds[f"{table}.{fieldname}"] = kind

    pairs: list[dict] = []
    for a, va in values.items():
        if len(va) < MIN_DISTINCT:
            continue
        a_table = a.split(".", 1)[0]
        for b, vb in values.items():
            if a == b or b.split(".", 1)[0] == a_table or not vb:
                continue
            # Comparing a quantity against a document number is noise, and an
            # equality test on mixed types would silently coerce.
            if kinds[a] != kinds[b] or kinds[a] in ("empty", "boolean"):
                continue
            ratio = len(va & vb) / len(va)
            if ratio >= REPORT_THRESHOLD:
                pairs.append({
                    "from": a, "to": b,
                    "containment": round(ratio, 4),
                    "matched": len(va & vb),
                    "from_distinct": len(va),
                    "to_distinct": len(vb),
                })

    pairs.sort(key=lambda p: (-p["containment"], p["from"], p["to"]))
    return pairs, values


# ======================================================================
# Assembly
# ======================================================================
def build_profile(data_dir: Path | None = None) -> dict:
    tables = load_tables(data_dir)
    columns = [
        profile_column(table, fieldname, rows)
        for table, rows in tables.items()
        for fieldname in _columns_of(rows)
    ]
    pairs, _ = containment(tables)

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_dir": str(data_dir or DATA_DIR),
        "method": "deterministic",
        "thresholds": {
            "foreign_key": FK_THRESHOLD,
            "reported": REPORT_THRESHOLD,
            "min_distinct": MIN_DISTINCT,
        },
        "tables": [
            {"table": t, "rows": len(rows), "columns": len(_columns_of(rows))}
            for t, rows in sorted(tables.items())
        ],
        "columns": columns,
        "containment": pairs,
        "note": (
            "containment[i] = |distinct(from) & distinct(to)| / |distinct(from)|, "
            "computed over the generated tables with no model involvement. "
            f"Pairs below {REPORT_THRESHOLD} are omitted; the near misses between "
            f"{REPORT_THRESHOLD} and {FK_THRESHOLD} are kept so rejected "
            "candidates stay visible."
        ),
    }


def containment_index(profile: dict) -> dict[tuple[str, str], float]:
    """(from_field, to_field) -> ratio, for O(1) evidence lookup."""
    return {(p["from"], p["to"]): p["containment"] for p in profile.get("containment", [])}


def column_index(profile: dict) -> dict[str, dict]:
    return {f"{c['table']}.{c['field']}": c for c in profile.get("columns", [])}


def write(path: Path | None = None, data_dir: Path | None = None) -> Path:
    out = path or (ARTIFACTS_DIR / "profile.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_profile(data_dir), indent=2))
    return out


def load(path: Path | None = None, data_dir: Path | None = None) -> dict:
    """The profile from disk, recomputed in memory if it was never written.

    Recomputing rather than writing keeps a GET request side-effect free.
    """
    src = path or (ARTIFACTS_DIR / "profile.json")
    if src.exists():
        try:
            return json.loads(src.read_text())
        except Exception:
            pass
    return build_profile(data_dir)


if __name__ == "__main__":
    p = build_profile()
    out = write()
    strong = [c for c in p["containment"] if c["containment"] >= FK_THRESHOLD]
    print(f"  {len(p['tables'])} tables, {len(p['columns'])} columns")
    print(f"  {len(p['containment'])} containment pairs >= {REPORT_THRESHOLD}, "
          f"{len(strong)} >= {FK_THRESHOLD}")
    print(f"  -> {out}")
