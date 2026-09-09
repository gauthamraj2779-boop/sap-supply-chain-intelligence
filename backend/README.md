# AI-Powered SAP Knowledge Graph
### Self-Healing Supply Chain Intelligence

Multi-hop supplier-delay impact analysis over an SAP-derived knowledge graph —
with dollar-denominated exposure, preventive avoidance planning, SAP source
lineage, and explainable confidence.

> **"Before a supplier delay cascades into missed customer deliveries, the system
> has already priced the damage, found the alternate sources, and shown its
> working — back to the SAP table cell."**

---

## The question this answers

> *If a supplier is delayed, which materials, plants, production orders and
> customer deliveries will be affected, and why?*

That is an **eight-hop traversal**:

```
Supplier ─▶ PurchaseOrder ─▶ ScheduleLine ─▶ Material@Plant
         ─▶ ProductionOrder ─▶ SalesOrder ─▶ Delivery ─▶ Customer
   LFA1        EKKO/EKPO          EKET         MARA/MARC/MARD
                                            AFKO/AFPO/RESB   VBAK/VBAP  LIKP/LIPS  KNA1
```

Why the obvious approaches fall short:

| Approach | Why it fails here |
|---|---|
| **SQL** | All eight joins must be written *before* the question is asked. A new question needs a new query from an SAP expert; traversal depth is fixed at design time. |
| **Vector search / RAG** | Retrieves text that *mentions* a supplier. "Which production orders consume this supplier's material" is a traversal, not a similarity — structurally out of reach. |
| **Bare LLM** | Invents relationships that don't exist in *your* configuration, and cannot do stock arithmetic against real rows. |

---

## Three things that make this more than a graph demo

### 1. It speaks in dollars, not nodes

Every hop is priced, and the total is decomposable:

| Component | Derived from | Example |
|---|---|---|
| PO stranded value | `EKPO.NETWR` on lines whose material actually goes short | $504,000 |
| Production halt cost | longest halt per plant × idle cost/day | $3,900,000 |
| Revenue at risk | `VBAP.NETWR` of affected sales order items | $84,900,000 |
| Penalty exposure | order value × contractual late-delivery rate | $6,248,000 |
| **Total** | | **$95,552,000** |

Every figure that is **not** an SAP field — idle plant cost, penalty rates — is
returned in an `assumptions` array rather than buried in a constant. The plant
idle cost lives on the `Plant` node in the data, labelled `_assumption`.

### 2. It prevents rather than alerts

When a shortfall is found the engine queries the graph *in reverse* for ways to
not have the problem, then allocates the shortfall **greedily by marginal cost
per unit covered**:

| Strategy | SAP source | Question it answers |
|---|---|---|
| Alternate supplier | `EINA`/`EINE` | Who else is approved to supply this, fast enough to beat the delay? |
| Cross-plant transfer | `MARD`/`MARC` | Is there spare stock elsewhere, above safety stock and not locally needed? |
| Production re-sequencing | `AFKO`/`RESB` | Can we defer an order no customer is waiting on, and reallocate its components? |

On the reference scenario: **$95.6M exposure reduced to $5.7M for $7,414** —
94% mitigated. Options that were evaluated and *rejected* are returned too, with
the per-unit cost that lost, so the decision is inspectable rather than asserted.

### 3. No dollar figure ever originates in a language model

| Layer | Role | When it fails |
|---|---|---|
| **Deterministic** — traversal, shortfall, financial, avoidance | The authority. Pure Python + graph queries. | Partial hops are reported; confidence drops; completed hops still return. |
| **Generative** — question parsing, narrative prose | Phrases results; parses questions. Never computes. | Narrative is omitted. Every number is unaffected. |
| **Validation** — cross-check, SHACL, confidence | Extracts every monetary figure from the prose and matches it against computed values. | Divergence >5% is flagged; the computed value wins and the discrepancy is reported. |

Degradation is tested, not asserted — see `tests/test_faulttolerance.py`.

---

## Quick start

**No credentials of any kind are required.**

```bash
cd backend
make setup      # venv (Python 3.12) + dependencies
make data       # generate the SAP-faithful dataset
make test       # 63 tests
make run        # http://localhost:8000/docs
```

Then, in another terminal:

```bash
make check      # end-to-end smoke test of the whole demo path
```

```bash
curl -s -X POST localhost:8000/api/query \
  -H 'content-type: application/json' \
  -d '{"question":"Supplier Apex Microelectronics is delayed by 14 days. What'\''s our exposure?"}'
```

### Optional: add capability

| Add | Unlocks | How |
|---|---|---|
| Neo4j Aura Free | Real graph database, raw Cypher endpoint | Instance at [console.neo4j.io](https://console.neo4j.io) → `NEO4J_*` in `.env` → `GRAPH_BACKEND=neo4j` → `make load` |
| Any LLM key | Prose narrative, LLM-assisted question parsing | `LLM_PROVIDER` + key in `.env` |

Supported providers: `openai`, `deepseek`, `groq`, `azure` (OpenAI-wire-compatible,
one code path) and `gemini`. `/api/health` always reports exactly which
capabilities are live.

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

## Architecture

```
                  ┌──────────────────────────────────────────┐
 POST /api/impact │   Orchestrator  (engines/orchestrator)   │
 POST /api/query  └────────────────────┬─────────────────────┘
                                       │
     ┌─────────────────────────────────┼──────────────────────────────┐
     ▼                                 ▼                              ▼
┌──────────────┐            ┌────────────────────┐        ┌────────────────────┐
│DETERMINISTIC │            │    GENERATIVE      │        │     VALIDATION     │
│ (authority)  │            │    (optional)      │        │                    │
├──────────────┤            ├────────────────────┤        ├────────────────────┤
│ traversal    │            │ NL → parameters    │        │ cross_check        │
│ shortfall    │            │ narrative prose    │        │ shacl_validator    │
│ financial    │            │                    │        │ confidence         │
│ avoidance    │            │ absent → omitted   │        │ LLM ≠ math → math  │
└──────┬───────┘            └────────────────────┘        └────────────────────┘
       ▼
┌───────────────────────────────┐
│ GraphBackend (semantic surface)│
│   ├── Neo4jBackend   (Cypher)  │
│   └── MemoryBackend  (in-proc) │
└───────────────────────────────┘
```

Engines call **semantic methods** (`reservations_for(matnr, werks)`), never raw
query strings. That is what makes the two backends interchangeable and every
engine unit-testable without a database.

---

## Data

Synthetic, SAP-structured: real DDIC table and field names, authored values.
17 tables, 221 records.

`LFA1` · `KNA1` · `MARA` · `MARC` · `MARD` · `T001W` · `EINA`/`EINE` · `EKKO` ·
`EKPO` · `EKET` · `AFKO` · `AFPO` · `RESB` · `VBAK` · `VBAP` · `LIKP` · `LIPS`

**On the record:** the data is synthetic. The *structure* is not — table names,
field names, key relationships and cardinalities are genuine SAP. Swapping the
generator for an SAP OData/RFC extract changes one module (the loader); the
graph, the ontology, the arithmetic and the validation are untouched.

Three conditions are deliberately planted, and asserted in `tests/test_generate.py`:

1. **Apex Microelectronics** sole-sources `MCU-32` and `PWR-IC-7`, both feeding
   near-term aerospace deliveries, both thinly stocked at plant 1010.
2. **Nova Components** is an approved alternate for `MCU-32` (4-day lead time);
   plant 1020 holds transferable stock; two production orders carry no customer
   commitment. Three genuine rescue routes.
3. **Toshiro Metals** is deeply stocked — the contrast case. A 14-day delay
   there must return **zero exposure**. A system that alarms on every supplier
   is not reasoning, so this is a test, not a footnote.

---

## Verification

```bash
make test    # 63 tests
make check   # end-to-end against a live server
```

The financial tests assert **hand-computed values**, not just internal
consistency:

- `MCU-32 @ 1010`: `MARD.LABST` 850; `RESB.BDMNG` 2000 + 900 + 800 = 3,700 due
  before the revised arrival; sole-sourced so other inbound = 0.
  **Shortfall = 3,700 − 850 = 2,850 units.**
- Order `000009001` needs `MCU-32` on D+8; the delayed PO now lands D+20.
  **Halt = 12 days.**
- Plant 1010: 12 disrupted days × $180,000 = $2,160,000. Plant 1020: 12 × $145,000
  = $1,740,000. **Halt cost = $3,900,000.**

Also asserted: concurrent halts at one plant are **not** double-billed; a
covered material never halts production; a longer delay never *reduces* impact;
and every impact row carries a lineage trail resolving to a real record.

---

## Project layout

```
backend/
├── app/
│   ├── config.py              every credential optional
│   ├── main.py                FastAPI app, startup degradation
│   ├── engines/
│   │   ├── deterministic.py   8-hop traversal + shortfall  ← the authority
│   │   ├── financial.py       the only source of dollar figures
│   │   ├── avoidance.py       alternate sources, transfers, re-sequencing
│   │   ├── generative.py      NL parsing + prose (both degradable)
│   │   ├── llm.py             5 providers; never raises
│   │   └── orchestrator.py    pipeline assembly
│   ├── validation/
│   │   ├── cross_check.py     LLM figures vs computed figures
│   │   ├── shacl_validator.py the governance gate
│   │   └── confidence.py      3 published components
│   ├── graph/
│   │   ├── schema.py          SAP → business ontology mapping
│   │   ├── adapter.py         semantic query surface + backend factory
│   │   ├── backends/          neo4j_backend.py, memory.py
│   │   ├── loader.py          JSON → Neo4j, idempotent, lineage on every edge
│   │   ├── ontology.py        emits OWL + SHACL from schema.py
│   │   └── ontology.ttl       generated
│   ├── routers/               health, impact, query, graph
│   └── models/                pydantic response contracts
├── data/synthetic/            generator + 17 generated tables
├── scripts/smoke_test.py      end-to-end demo-path check
└── tests/                     63 tests, no credentials needed
```
