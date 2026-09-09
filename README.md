# SAP Knowledge Graph — Self-Healing Supply Chain Intelligence

An AI-powered SAP Knowledge Graph analyst console that performs deep multi-hop supply chain impact analysis, computes financial exposure down to sales orders and customers, and generates ROI-optimized mitigation avoidance plans with full audit lineage.

---

## 🌟 Key Capabilities

- **Editorial Analyst Console UI**: Clean, high-density editorial design system featuring serif typography (`Fraunces`), clean sans (`IBM Plex Sans`), and tabular numeric code styling (`IBM Plex Mono`).
- **Interactive Multi-Hop Blast Radius**: Cytoscape.js directed graph visualization mapping disruptions across `Suppliers -> Purchase Orders -> Materials -> Plants -> Production Orders -> Sales Orders -> Deliveries -> Customers`.
- **Financial Exposure Breakdown**: Ledger breakdown of total financial exposure ($3.84M) including Purchase Orders, Production Halt costs, Revenue at Risk, and Contract Penalties.
- **Dynamic Avoidance Plan**: Prioritized actions (Emergency Air Freight, Buffer Inventory Allocation, Line Rebalancing) with estimated ROI, risk mitigation, and lead times.
- **Horizontal Alternating Timeline**: Phase-by-phase timeline displaying critical operational milestones and cumulative exposure growth over time.
- **Audit Lineage & Data Trust**: Drilldown into raw SAP tables (`EKKO`, `EKPO`, `MARA`, `VBAK`, `VBAP`, `LIKP`, `KNA1`) with traversal coverage and confidence scoring.

---

## 🏗️ Architecture

```
sap/
├── frontend/                     # React + Vite frontend application
│   ├── src/
│   │   ├── components/
│   │   │   ├── QueryInput.jsx          # Plain search console + quick query chips
│   │   │   ├── BlastRadiusGraph.jsx    # Cytoscape.js interactive topology
│   │   │   ├── FinancialDashboard.jsx  # Ledger breakdown & customer risk
│   │   │   ├── AvoidancePanel.jsx      # Mitigation plan with execution actions
│   │   │   ├── ImpactTimeline.jsx      # Horizontal alternating timeline
│   │   │   └── LineageTrail.jsx        # SAP table audit trail
│   │   ├── utils/
│   │   │   ├── api.js                  # API service with graceful mock fallback
│   │   │   └── graphLayout.js          # Cytoscape cose-bilkent layout & styling
│   │   ├── App.jsx                     # Left-rail navigation & section orchestrator
│   │   ├── index.css                   # Custom theme & typography tokens
│   │   └── main.jsx                    # React entry point
│   ├── package.json
│   └── vite.config.js                  # Proxy configuration to backend (:8000)
├── implementation_plan.md              # Technical specification & architecture docs
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites
- Node.js (v18+)
- npm or yarn

### Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```
The application will launch on `http://localhost:5173`.

> **Note**: If no backend is running on `http://localhost:8000`, the frontend automatically runs in **Demo Mode** with full mock data and simulation features enabled.

---

## 🔌 Backend API Integration

The frontend seamlessly connects to a FastAPI/Python backend running on `http://localhost:8000`.

### Required Endpoints:
1. `GET /api/health` — Returns status (`{"status": "ok"}`)
2. `POST /api/query` — Accepts `{"query": "string"}` and extracts entity parameters (`{"supplier_id": "SUP-1000", "delay_days": 14}`)
3. `POST /api/impact` — Accepts `{"supplier_id": "...", "delay_days": N}` and returns the complete `ImpactReport` JSON payload.
