# Deployment

Nothing is deployed yet. This is the runbook.

The system is designed to run with **no credentials at all** — the in-process
graph and the deterministic engines produce the complete financial report on
their own. So the first deploy needs no database and no LLM key; both are
optional upgrades you can add later without touching code.

---

## What ships where

| Piece | Where | Cost |
|---|---|---|
| Backend (FastAPI) | Render, from `backend/Dockerfile` | Free tier |
| Frontend (static Vite build) | GitHub Pages, via Actions | Free |
| Graph database | Neo4j Aura Free — optional | Free |
| LLM | Any of five providers — optional | Varies |

Everything needed is in the repo: `backend/Dockerfile`, `render.yaml`,
`.github/workflows/ci.yml`, `.github/workflows/deploy-frontend.yml`.

---

## 1. Backend → Render

1. render.com → **New** → **Blueprint** → point it at this repository.
   It reads `render.yaml` and builds `backend/Dockerfile`.
2. Set `CORS_ORIGINS` to the frontend origin once you have it (step 2), e.g.
   `https://gauthamraj2779-boop.github.io`.
3. Deploy. Health check is `/api/health`; the container reports healthy only
   once the graph has loaded.

**Free tier sleeps after ~15 minutes idle** and takes 30–60 seconds to wake.
Before a live demo, open the API once to warm it.

Optional environment variables, all settable in the Render dashboard with no
redeploy of code:

```
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=...        AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
GRAPH_BACKEND=neo4j
NEO4J_URI=...  NEO4J_USER=neo4j  NEO4J_PASSWORD=...
```

---

## 2. Frontend → GitHub Pages

1. Repository **Settings → Pages → Source: GitHub Actions**.
2. Repository **Settings → Secrets and variables → Actions → Variables**, add:
   `VITE_API_URL` = the Render backend URL (e.g. `https://sap-kg-api.onrender.com`).
3. Push to `main`. `deploy-frontend.yml` builds and publishes.

The site lands at `https://<owner>.github.io/sap-supply-chain-intelligence/`.
`vite.config.js` reads `VITE_BASE_PATH` so assets resolve under the repo
subpath; local development is unaffected.

**Order matters:** deploy the backend first, set `VITE_API_URL`, then let the
frontend build. A frontend built without it will try `localhost:8000` and show
its "backend unreachable" state — correct behaviour, but not a demo.

---

## 3. Neo4j Aura — optional

The Neo4j driver, loader, uniqueness constraints and Cypher backend are written
and tested, but **no instance is configured**, so every query currently runs on
the in-process graph. `/api/health` reports `backend: memory`.

To switch it on:

1. console.neo4j.io → **New Instance** → **AuraDB Free**.
   **Save the password when it is shown — it is shown once.**
2. Locally, put `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` in `backend/.env`,
   set `GRAPH_BACKEND=neo4j`, and run `make load`.
3. Set the same variables on Render.

Results are identical either way — that is asserted by the test suite. What you
gain is a real database in the architecture diagram and the `POST /api/cypher`
endpoint, which the in-process backend refuses.

Free tier: 200k nodes / 400k relationships against a dataset of a few hundred.
It **pauses after 3 days without writes** and is deleted after 30 days paused —
resume it before a demo.

---

## 4. CI

`ci.yml` runs on every push and pull request:

- Backend: full test suite, then a live-server smoke test over the whole demo path
- Frontend: production build

Both run **with no credentials**, which is the point — if the suite ever needs a
key to pass, the degradation guarantee has been broken.

---

## Demo-day checklist

1. Wake the Render backend (open `/api/health`) — free tier sleeps
2. If using Aura, confirm the instance is resumed, not paused
3. Load the frontend and run one query end to end
4. Check the top bar reads **Computed live**, not **Backend unreachable**

---

## Alternatives

| Instead of | Use | Note |
|---|---|---|
| Render | Fly.io, Railway, Azure App Service | Any Docker host; the image is standard |
| GitHub Pages | Vercel, Netlify, Cloudflare Pages | Any static host; set `VITE_API_URL` at build time |
| Both split | One container serving the built frontend from FastAPI | Simplest single-URL demo; needs a small static-mount change in `main.py` |
