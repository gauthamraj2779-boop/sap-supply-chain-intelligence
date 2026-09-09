# SAP Knowledge Graph — Self-Healing Supply Chain Intelligence

An AI-powered SAP knowledge graph console that performs multi-hop supply chain impact
analysis, prices the exposure down to individual customer deliveries, and generates
ROI-ranked mitigation plans with full audit lineage back to SAP table cells.

> **"Before a supplier delay cascades into missed customer deliveries, the system has
> already priced the damage, found the alternate sources, and shown its working."**

---

## The question this answers

> *If a supplier is delayed, which materials, plants, production orders and customer
> deliveries will be affected, and why?*

That is an **eight-hop traversal**:

```
Supplier ─▶ PurchaseOrder ─▶ ScheduleLine ─▶ Material@Plant
         ─▶ ProductionOrder ─▶ SalesOrder ─▶ Delivery ─▶ Customer
   LFA1        EKKO/EKPO         EKET        MARA/MARC/MARD
                                       AFKO/AFPO/RESB  VBAK/VBAP  LIKP/LIPS  KNA1
```

| Approach | Why it falls short |
|---|---|
| **SQL** | All eight joins must be written *before* the question is asked. A new question needs a new query from an SAP expert; traversal depth is fixed at design time. |
| **Vector search / RAG** | Retrieves text that *mentions* a supplier. "Which production orders consume this supplier's material" is a traversal, not a similarity. |
| **Bare LLM** | Invents relationships that don't exist in *your* configuration, and cannot do stock arithmetic against real rows. |

---

## Three things that make this more than a graph demo

### 1. It speaks in dollars, not nodes

| Component | Derived from |
|---|---|
| PO stranded value | `EKPO.NETWR` on lines whose material actually goes short |
| Production halt cost | longest halt per plant × idle cost/day |
| Revenue at risk | `VBAP.NETWR` of affected sales order items |
| Penalty exposure | order value × contractual late-delivery rate |

Every figure that is **not** an SAP field — idle plant cost, penalty rates — is returned
in an `assumptions` array and rendered in the UI, rather than buried in a constant.

### 2. It prevents rather than alerts

When a shortfall is found the engine queries the graph *in reverse* and allocates the
shortfall **greedily by marginal cost per unit covered**:

| Strategy | SAP source | Question it answers |
|---|---|---|
| Alternate supplier | `EINA`/`EINE` | Who else is approved, fast enough to beat the delay? |
| Cross-plant transfer | `MARD`/`MARC` | Is there spare stock elsewhere, above safety stock and not locally needed? |
| Production re-sequencing | `AFKO`/`RESB` | Can we defer an order no customer is waiting on and reallocate its components? |

Options that were evaluated and **rejected** are shown too, with the per-unit cost that
lost — a decision is more credible when the road not taken is visible.

### 3. No dollar figure ever originates in a language model

| Layer | Role | When it fails |
|---|---|---|
| **Deterministic** — traversal, shortfall, financial, avoidance | The authority. Pure Python + graph queries. | Partial hops are reported; confidence drops; completed hops still return. |
| **Generative** — question parsing, narrative prose | Phrases results; parses questions. Never computes. | Narrative is omitted; every number is unaffected. |
| **Validation** — cross-check, SHACL, confidence | Extracts every monetary figure from the prose and matches it against computed values. | Divergence >5% is flagged; the computed value wins. |

**The frontend has no mock data and no offline fallback.** If the backend cannot answer,
the console shows an error — never an invented figure.

---

## Quick start

**No credentials of any kind are required.** The backend runs on an in-process graph and
the console is fully functional without a database or an LLM key.

```bash
# Terminal 1 — backend  (http://localhost:8000/docs)
cd backend
make setup && make data && make run

# Terminal 2 — frontend (http://localhost:5173)
cd frontend
npm install && npm run dev
```

Verify the whole demo path end to end:

```bash
cd backend && make test && make check
```

### Optional: add capability

| Add | Unlocks | How |
|---|---|---|
| Neo4j Aura Free | Real graph database, raw Cypher endpoint | Instance at [console.neo4j.io](https://console.neo4j.io) → `NEO4J_*` in `backend/.env` → `GRAPH_BACKEND=neo4j` → `make load` |
| Any LLM key | Prose narrative, LLM-assisted question parsing | `LLM_PROVIDER` + key in `backend/.env` |

Supported providers: `openai`, `deepseek`, `groq`, `azure` (all OpenAI-wire-compatible,
one code path) and `gemini`. `/api/health` always reports which capabilities are live,
and the console's top bar reflects it.

---

## Architecture

```
├── backend/                      FastAPI + deterministic engines
│   ├── app/
│   │   ├── engines/
│   │   │   ├── deterministic.py  8-hop traversal + shortfall   ← the authority
│   │   │   ├── financial.py      the only source of dollar figures
│   │   │   ├── avoidance.py      alternate sources, transfers, re-sequencing
│   │   │   ├── generative.py     NL parsing + prose (both degradable)
│   │   │   ├── llm.py            5 providers; never raises
│   │   │   └── orchestrator.py   pipeline assembly
│   │   ├── validation/
│   │   │   ├── cross_check.py    LLM figures vs computed figures
│   │   │   ├── shacl_validator.py the governance gate
│   │   │   └── confidence.py     3 published components
│   │   ├── graph/
│   │   │   ├── schema.py         SAP → business ontology mapping
│   │   │   ├── adapter.py        semantic query surface + backend factory
│   │   │   ├── backends/         neo4j_backend.py · memory.py
│   │   │   ├── loader.py         JSON → Neo4j, idempotent, lineage on every edge
│   │   │   └── ontology.ttl      OWL + SHACL, generated from schema.py
│   │   └── routers/              health · impact · query · graph
│   ├── data/synthetic/           generator + 20 SAP-shaped tables
│   └── tests/                    85 tests, no credentials needed
└── frontend/                     React + Vite + Cytoscape.js
    └── src/
        ├── components/
        │   ├── QueryInput.jsx        console + live supplier autocomplete
        │   ├── BlastRadiusGraph.jsx  Cytoscape topology, sized by exposure
        │   ├── FinancialDashboard.jsx ledger + per-customer roll-up
        │   ├── AvoidancePanel.jsx    mitigation plan + SAP evidence
        │   ├── ImpactTimeline.jsx    when each domino falls
        │   └── LineageTrail.jsx      SAP source-record inspector
        └── utils/
            ├── api.js                API client + view-model adapter (no mocks)
            ├── format.js             presentation only
            └── graphLayout.js        Cytoscape styling
```

The backend's `GraphBackend` exposes **semantic methods** (`reservations_for(matnr, werks)`),
never raw query strings. That is what makes Neo4j and the in-process store interchangeable
and every engine unit-testable without a database.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | Status and per-capability availability |
| `GET  /api/suppliers` | Supplier roster with risk scores |
| `POST /api/impact` | Impact analysis for `{supplier_id, delay_days}` |
| `POST /api/query` | Natural-language question → full report |
| `GET  /api/query/examples` | Worked example questions |
| `POST /api/cypher` | Read-only Cypher (Neo4j backend only) |
| `GET  /api/graph` | Full graph snapshot for visualisation |
| `GET  /api/schema` | SAP table/field → business ontology mapping |
| `GET  /api/ontology` | OWL ontology + SHACL shapes (Turtle) |
| `GET  /api/validation` | SHACL governance report |
| `GET  /api/lineage/{type}/{id}` | SAP provenance for a node type |

---

## Data

Synthetic, SAP-structured: real DDIC table and field names, authored values.
20 tables, 275 records.

`LFA1` · `KNA1` · `MARA` · `MARC` · `MARD` · `T001W` · `EINA`/`EINE` · `EKKO` · `EKPO` ·
`EKET` · `MAST`/`STKO`/`STPO` · `AFKO` · `AFPO` · `RESB` · `VBAK` · `VBAP` · `LIKP` · `LIPS`

**On the record:** the data is synthetic; the *structure* is not. Table names, field names,
key relationships and cardinalities are genuine SAP. Swapping the generator for an SAP
OData/RFC extract changes one module — the loader. The graph, ontology, arithmetic and
validation are untouched.

Three conditions are deliberately planted and asserted in `tests/test_generate.py`:

1. **Apex Microelectronics** sole-sources `MCU-32` and `PWR-IC-7`, both feeding near-term
   aerospace deliveries, both thinly stocked at plant 1010.
2. **Nova Components** is an approved alternate for `MCU-32` (4-day lead time), plant 1020
   holds transferable stock, and two production orders carry no customer commitment.
3. **Toshiro Metals** is deeply stocked — the contrast case. A 14-day delay there returns
   **zero exposure**. A system that alarms on every supplier is not reasoning, so this is
   a test, not a footnote.

---

## Verification

```bash
cd backend
make test    # 85 tests, no credentials required
make check   # end-to-end smoke test against a live server
```

The financial tests assert **hand-computed values**, not just internal consistency:

- `MCU-32 @ 1010`: `MARD.LABST` 850; `RESB.BDMNG` 2000 + 900 + 800 = 3,700 due before the
  revised arrival; sole-sourced so other inbound = 0. **Shortfall = 2,850 units.**
- Order `000009001` needs `MCU-32` on D+8; the delayed PO lands D+20. **Halt = 12 days.**
- Plant 1010: 12 disrupted days × $180,000. Plant 1020: 12 × $145,000.
  **Halt cost = $3,900,000.**

Also asserted: concurrent halts at one plant are not double-billed; a covered material
never halts production; a longer delay never *reduces* impact; and every impact row
carries a lineage trail resolving to a real record.
