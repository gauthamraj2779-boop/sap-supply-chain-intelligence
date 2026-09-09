#!/usr/bin/env python
"""End-to-end smoke test against a live server.

Exercises the demo path exactly as the frontend will, and asserts the
properties the pitch depends on. Exits non-zero on any failure.

    make run          # in one terminal
    make check        # in another
"""

from __future__ import annotations

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -- ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def money(v: float) -> str:
    return f"${v:,.0f}"


def main() -> int:
    print(f"\nSmoke test against {BASE}\n" + "=" * 68)
    try:
        # /api/query can make two sequential model calls (parse, then
        # narrate). A reasoning model takes ~30s each, so 60s was not enough.
        c = httpx.Client(base_url=BASE, timeout=180.0)
        h = c.get("/api/health").json()
    except Exception as exc:
        print(f"  FAIL  cannot reach the API: {exc}\n  Start it with: make run")
        return 1

    print("\n[1] Health and capabilities")
    check("service is up", h["status"] == "ok")
    check("graph is loaded", h["graph"]["records"] > 0, f"{h['graph']['records']} records")
    check("financial quantification available",
          h["capabilities"]["financial_quantification"])
    print(f"        graph backend : {h['graph']['backend']}")
    print(f"        llm           : {h['llm']['provider']} "
          f"(available={h['llm']['available']})")

    print("\n[2] The flagship question")
    r = c.post("/api/query", json={
        "question": "Supplier Apex Microelectronics is delayed by 14 days. "
                    "What's our exposure?"
    }).json()
    check("question parsed", bool(r["interpreted"]["supplier_id"]),
          f"supplier={r['interpreted']['supplier_id']} "
          f"delay={r['interpreted']['delay_days']}d "
          f"via={r['interpreted']['parsed_by']}")
    rep = r["report"]
    fe = rep["financial_exposure"]
    print(f"\n        {rep['headline']}\n")
    check("exposure is non-zero", fe["total_financial_exposure"] > 0,
          money(fe["total_financial_exposure"]))
    parts = (fe["po_stranded_value"] + fe["production_halt_cost"]
             + fe["revenue_at_risk"] + fe["penalty_exposure"])
    check("components sum to the total",
          abs(parts - fe["total_financial_exposure"]) < 0.01)
    check("non-SAP inputs are declared", len(fe["assumptions"]) >= 3,
          f"{len(fe['assumptions'])} assumptions")

    print("\n[3] Multi-hop blast radius")
    t = rep["traversal"]
    for key, label in (("purchase_orders", "purchase orders"),
                       ("materials", "materials"),
                       ("production_orders", "production orders"),
                       ("sales_orders", "sales orders"),
                       ("deliveries", "deliveries")):
        check(f"reached {label}", bool(t[key]), str(len(t[key])))
    check("crossed plant boundaries", len(t["plants"]) >= 2,
          f"{len(t['plants'])} plants")
    check("all hops completed", t["hops_failed"] == [])

    print("\n[4] Lineage")
    # Show a material that actually goes short; a zero-shortfall row
    # makes for a confusing illustration of the arithmetic.
    sample = max(t["materials"], key=lambda m: m["shortfall_qty"])
    tables = {s["sap_table"] for s in sample["lineage"]["steps"]}
    check("every impact row cites SAP tables",
          all(m["lineage"]["steps"] for m in t["materials"]), ", ".join(sorted(tables)))
    check("derivation arithmetic is shown", bool(sample["lineage"]["derivation"]))
    print(f"        {sample['lineage']['derivation']}")

    print("\n[5] Avoidance")
    plan = rep["avoidance"]
    mit = ((plan["exposure_before"] - plan["exposure_after"])
           / max(plan["exposure_before"], 1))
    check("actions proposed", len(plan["actions"]) >= 2, f"{len(plan['actions'])} actions")
    check("mitigates most of the exposure", mit > 0.5, f"{mit:.1%}")
    check("costs less than it saves",
          plan["total_avoidance_cost"] < plan["total_risk_mitigated"],
          f"{money(plan['total_avoidance_cost'])} to remove "
          f"{money(plan['total_risk_mitigated'])}")
    for a in plan["actions"]:
        print(f"        - {a['title']}")
        print(f"            cost {money(a['cost'])}, mitigates {money(a['risk_mitigated'])}")

    print("\n[6] Confidence")
    conf = rep["confidence"]
    check("confidence is published with components", 0 <= conf["overall"] <= 1,
          f"{conf['overall']:.2f} (data {conf['data_completeness']}, "
          f"coverage {conf['traversal_coverage']}, "
          f"agreement {conf['engine_agreement']})")
    check("degraded modes are disclosed", isinstance(conf["degraded_modes"], list),
          ", ".join(conf["degraded_modes"]) or "none")

    print("\n[7] Governance")
    v = c.get("/api/validation").json()
    check("SHACL gate ran", v["available"], f"{v['nodes_validated']} nodes validated")
    o = c.get("/api/ontology").json()
    check("ontology carries SAP lineage", "sap:sourceTable" in o["content"],
          f"{o['bytes']} bytes of Turtle")

    print("\n[8] Contrast case: a well-stocked supplier must NOT alarm")
    d = c.post("/api/impact", json={"supplier_id": "0000001002",
                                    "delay_days": 14}).json()
    check("reports zero exposure",
          d["financial_exposure"]["total_financial_exposure"] == 0.0)
    check("proposes no actions", d["avoidance"]["actions"] == [])

    print("\n" + "=" * 68)
    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s)\n  " + "\n  ".join(FAILS))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
