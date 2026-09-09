# Improvements

Two gaps between what the problem statement asks for and what currently exists,
with a concrete plan for each.

---

## Audit against the original design document

The design doc described more than what exists. Checked against the code:

| Design doc said | Reality |
|---|---|
| Neo4j Cypher traversal | **Not running.** The driver, loader, constraints and Cypher are all written and tested, but no Aura instance is configured, so every query runs on the in-process backend. `/api/health` reports `backend: memory` |
| `MAST`/`STPO` BOM tables, `:BOMItem`, `COMPONENT_OF`, `ASSEMBLES_INTO` | **Not implemented.** Component requirements come from `RESB` only. There is no bill of materials, so multi-level explosion (sub-assembly inside a finished good) is not modelled |
| LLM "Query → Cypher translation" | **Not implemented.** Natural language maps to `{supplier_id, delay_days}`, not to Cypher. Deliberate — a generated query cannot be verified before it runs — but it is not what the doc claimed |
| LLM "Action Plan Writer" | **Not implemented.** Action titles and descriptions are Python f-strings built from real values |
| Fault case: missing `NETWR` falls back to historical averages | **Not implemented.** A missing value lowers `data_completeness` and therefore confidence; nothing is estimated |
| Financial quantification | **Done** — four components, reconciled, per-customer roll-up |
| Avoidance: alternate supplier, safety stock, re-sequencing, cross-plant transfer | **Done** — all four exist. Cross-plant transfer is usually out-priced by re-sourcing and shows in "considered and rejected" |
| SHACL validation, cross-check, confidence | **Done** |
| Fault case: LLM down | **Done and tested** |
| Fault case: LLM disagrees with the maths | **Done and tested** |
| Frontend components | **Done**, all reading live API data |

The headline figures in the design doc ($53.6M, 47 deliveries, 23 production
orders) were illustrative. Real data produces $95,552,000 across 6 deliveries,
5 production orders and 2 plants.

**Fixed during this audit:** three commercial constants in `avoidance.py`
(2,500 rush fee, 2% handling, 3,500 freight) were used in the action costs but
appeared in no assumptions list — the $7,414 headline included an undeclared
2,500. They are now returned on the plan and rendered in the UI, with a
regression test.

---

## Where we actually stand

| Problem statement requirement | Status | Evidence |
|---|---|---|
| Discovers entities and relationships from SAP metadata and data | **Not built** | `schema.py` is hand-authored; no profiler, no discovery step |
| Converts technical SAP structures into a business ontology | **Partial** | `ontology.py` emits real OWL + SHACL — but from a hand-written mapping, not a discovered one |
| Populates a governed knowledge graph with actual SAP records | **Done** | SHACL gate at startup, `_source_table`/`_source_key` on every node, `_derived_from` on every edge |
| Natural-language, multi-hop reasoning across connected business objects | **Partial** | The 8-hop traversal is real; the "reasoning" is a fixed `for` loop, and NL parsing works without an LLM |
| Explainable answers with calculations, source lineage and confidence | **Done** | Per-row derivations, 16-step critical path, 3-component confidence |

### What the LLM does today

Two calls, both optional:

| Location | Purpose | Required? |
|---|---|---|
| `app/engines/generative.py:140` | Question → `{supplier_id, delay_days}` | No — a regex parser handles it when no key is set |
| `app/engines/generative.py:186` | Writes the executive summary | No — the report is complete without prose |

Remove the API key and every figure is unchanged. That is a deliberate property
(see `validation/cross_check.py`), but it means the system is **AI-assisted, not
AI-driven**, and there is no agent: a grep for tool-calling, function-calling or
any planning loop returns nothing.

---

## A — Discovery agent

**Closes:** "Discovers entities and relationships from SAP metadata and data",
and upgrades the ontology row from *authored* to *discovered*.

**Why it matters more than it sounds.** Right now the honest answer to "how did
you decide `EKPO.LIFNR` points at `LFA1`?" is "a developer wrote it down." The
problem statement asks for that step to be discovered. It is also the cheapest
way to make the phrase "AI-powered" true of the pipeline rather than of the
prose.

### Inputs

1. **Real SAP OData `$metadata`** — free with an SAP Community account at
   `api.sap.com`. Static XML per service, containing genuine `EntityType`
   definitions, key properties and `NavigationProperty` declarations. Five
   services cover the chain:

   | Service | Provides |
   |---|---|
   | `API_BUSINESS_PARTNER` | `A_Supplier`, `A_Customer` |
   | `API_PRODUCT_SRV` | `A_Product` |
   | `API_PURCHASEORDER_PROCESS_SRV` | PO header, item, schedule line |
   | `API_PRODUCTION_ORDER_2_SRV` | Production order + components |
   | `API_OUTBOUND_DELIVERY_SRV` | Delivery header and item |

   Fetch with header `apikey: <key>` against
   `https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/<service>/$metadata`.
   **Cache to disk.** Never call the API during a demo.

2. **A DDIC-style catalog** over the generated tables — per field:
   `{table, field, key_flag, data_element, description, check_table}`. Check
   tables are SAP's foreign keys and the strongest signal available.

3. **Deterministic column profile** — cardinality, null rate, and the
   **containment ratio** `|A ∩ B| / |A|` between candidate join columns. A ratio
   ≥ 0.95 into a key column is hard evidence, independent of the model's opinion.

### Build

| File | Job |
|---|---|
| `app/ingest/sapapi.py` | Fetch + cache the five `$metadata` docs, parse EDMX into `{entity_type, keys, properties, navigation_properties}`. Wrap every call in try/except with a cached fallback |
| `app/discovery/profile.py` | Column profiler and containment matrix. No LLM |
| `app/discovery/discover.py` | One structured-output call. Input: DDIC catalog + `$metadata` summary + profile. Output below |
| `artifacts/discovery.json` | Reviewed once by hand, then committed |

Output schema:

```json
{
  "entities": [{
    "name": "Supplier", "source_table": "LFA1", "key_fields": ["LIFNR"],
    "business_definition": "...", "confidence": 0.98,
    "evidence": ["DD03L key flag on LIFNR", "OData EntityType A_Supplier key=Supplier"]
  }],
  "relationships": [{
    "name": "orderedFrom", "from": "PurchaseOrder", "to": "Supplier",
    "cardinality": "n:1",
    "join": {"from_field": "EKKO.LIFNR", "to_field": "LFA1.LIFNR"},
    "confidence": 0.97, "inferred": false,
    "evidence": ["check_table=LFA1", "containment 1.00",
                 "OData NavigationProperty to_Supplier"]
  }]
}
```

`schema.py` then reads `discovery.json` instead of hardcoding, and
`ontology.py` is unchanged — it already generates OWL + SHACL from whatever
schema it is given.

### The detail that proves it is real inference

Deliberately omit `check_table` on two or three genuine relationships in the
generated DDIC catalog — `LIPS.VGBEL → VBAK.VBELN` is the natural candidate.
The profiler will still show ~1.0 containment, and the model must infer the
relationship from data overlap rather than read it from a lookup. Those
relationships come back with `"inferred": true` and a lower confidence, which
is exactly the behaviour to demonstrate.

### UI

A **Discovery** tab: the DDIC catalog, the containment heatmap, and
`discovery.json` rendered with confidence bars and evidence — with the inferred
relationships highlighted.

### Verification

- Spot-check three relationships by hand against the DDIC catalog
- Assert the deliberately-omitted relationships are found and marked `inferred`
- `rdflib` parses the regenerated `ontology.ttl`; every class carries `sap:sourceTable`
- The existing 67 tests still pass against the discovered schema

**Effort:** ~2 hours. **Risk:** low — runs once, output is committed, nothing
on the demo path calls it live.

---

## B — Agent loop with a visible trajectory

**Closes:** "natural-language, multi-hop **reasoning**", and gives the console
something to show for the word *agent*.

**What it fixes.** Today the traversal order is fixed in code. It cannot answer
anything the fixed path was not written for — "which customers are exposed to
Taiwan?", "what if plant 1010 goes offline?", "compare Apex against Nova" — and
there is no reasoning to display because none happens.

### Design

Give the model tools and let it choose. Keep the flagship answer deterministic.

```
app/agent/
├── tools.py       tool definitions + handlers
├── loop.py        the agentic loop
└── trace.py       structured trajectory record
```

| Tool | Wraps | Notes |
|---|---|---|
| `get_ontology_schema()` | `schema.py` | Grounds the model so it cannot invent labels |
| `supplier_delay_impact(supplier_id, delay_days)` | `impact.py` unchanged | **The authority.** The flagship question resolves here |
| `find_material_stock(matnr, werks?)` | `MARD`/`MARC` | |
| `find_reservations(matnr, werks)` | `RESB` | |
| `trace_downstream(aufnr)` | production → sales → delivery → customer | |
| `find_alternate_sources(matnr)` | `EINA`/`EINE` | |
| `run_cypher(query)` | read-only, guarded | Neo4j backend only |
| `lineage(node_type, node_id)` | `schema.py` | |

Loop: call the model with the tool list → execute what it asks for → append
results → repeat until it stops or hits a step cap (8 steps, then it must
answer with what it has).

### The trajectory record

Every step captured:

```json
{
  "step": 3,
  "thought": "MCU-32 is short at 1010. I need to know which production orders consume it.",
  "tool": "find_reservations",
  "args": {"matnr": "MCU-32", "werks": "1010"},
  "result_summary": "3 reservations: 9001 (2,000 @ D+8), 9002 (900 @ D+9), 9003 (800 @ D+10)",
  "sap_tables_touched": ["RESB"],
  "duration_ms": 12
}
```

Rendered as a **Trajectory** tab: a step-by-step list showing what it decided,
which tool it reached for, which SAP tables it touched, and what came back. That
is the "what is the agent thinking" view.

### The safety property that must not be lost

`supplier_delay_impact` stays deterministic Python. The agent decides *when* to
call it; it never recomputes the answer itself. Everything already in place —
`cross_check.py`, the confidence score, the assumptions array — continues to
apply. **A wrong tool choice produces a worse answer, never a wrong number.**

### Demo sequencing

Run the flagship question first: the agent calls `supplier_delay_impact` once
and the familiar report appears, with a three-step trajectory. *Then* ask
something the fixed path could never handle, and let the audience watch it work
the problem across six or seven tool calls. That contrast is the demo.

### Verification

- Flagship question produces an identical financial report to the current build
- Every trajectory step names at least one real SAP table
- Step cap holds: a deliberately vague question terminates and says what it lacks
- With no LLM key: `/api/impact` still returns the full report; only the agent
  endpoint reports unavailable

**Effort:** ~3 hours. **Risk:** medium — an agent picking its own path is less
predictable on stage. Mitigated by keeping `impact.py` authoritative and routing
the demo question through it.

---

## Suggested order

Do **A** first if there is time for only one. It closes an explicit bullet of
the problem statement, it is low-risk, and "the ontology was discovered from
SAP's own metadata" is a stronger claim than a nicer trajectory panel.

Do **B** as well if there is time. Together they change the honest description
of this system from *a deterministic engine with an LLM writing prose* to *an
agent reasoning over a knowledge graph that it discovered from SAP metadata* —
which is what the problem statement actually asks for.

---

## Smaller items

- **Neo4j** — `GRAPH_BACKEND=neo4j` + `make load` against an Aura Free instance.
  Enables `POST /api/cypher` and a real database for the demo. ~20 min including signup.
- **Rotate the Azure key** — it was shared in plaintext during development.
- **Bundle size** — the frontend build warns above 500 kB; Cytoscape is most of
  it and could be dynamically imported so the landing page loads faster.
