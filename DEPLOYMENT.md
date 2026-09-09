# Deployment

Nothing is deployed yet. This is the runbook.

The system is designed to run with **no credentials at all** — the in-process
graph and the deterministic engines produce the complete financial report on
their own. So the first deploy needs no database and no LLM key; both are
optional upgrades you can add later without touching code.

---

## What ships where

**One service, one URL.** The Docker image builds the console and the API
serves it from the same process, so there is no CORS to configure, no second
host, and no ordering dependency between deploying the API and building a
console that needs to know the API's address.

| Piece | Where | Cost |
|---|---|---|
| API + console (one image) | Render, from `backend/Dockerfile` | Free tier |
| Graph database | Neo4j Aura Free — optional | Free |
| LLM | Any of five providers — optional | Varies |

### Why not GitHub Pages

The first attempt published the console to Pages and failed:

```
Error: Failed to create deployment (status: 404)
Ensure GitHub Pages has been enabled
```

The build succeeded; only the deploy step failed. Enabling Pages requires
**repository admin**, which a collaborator does not have — only the repo owner
can turn it on. Rather than block on that, the console is now served by the API
itself, which is a better arrangement anyway: one URL, no CORS, and nothing to
enable.

If you later want Pages as well, the owner enables it at
Settings → Pages → Source: GitHub Actions, and a workflow can be restored.

---

## 1. Deploy

1. render.com → **New** → **Blueprint** → point it at this repository.
   It reads `render.yaml` and builds `backend/Dockerfile` from the repo root,
   so the image can compile the frontend and copy it into `app/static`.
2. Deploy. Health check is `/api/health`; the container reports healthy only
   once the graph has loaded.
3. Open the service URL. The console is at `/`, the API docs at `/docs`.

No credentials are required for this step. The in-process graph and the
deterministic engines produce the complete financial report on their own.

**Free tier sleeps after ~15 minutes idle** and takes 30–60 seconds to wake.
Open the URL once before a live demo.

Optional environment variables, settable in the Render dashboard with no code
change:

```
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=...        AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
GRAPH_BACKEND=neo4j
NEO4J_URI=...  NEO4J_USER=neo4j  NEO4J_PASSWORD=...
```

---

## 2. Run the same image locally

```bash
docker build -f backend/Dockerfile -t sap-kg .
docker run -p 8000:8000 sap-kg
```

Then open http://localhost:8000.

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

1. Wake the service (open the URL) — the free tier sleeps after ~15 min idle
2. If using Aura, confirm the instance is resumed, not paused
3. Run one query end to end
4. Check the top bar reads **Computed live**, not **Backend unreachable**

---

## Alternatives

| Instead of | Use | Note |
|---|---|---|
| Render | Fly.io, Railway, Azure App Service | Any Docker host; the image is standard |
| One image | Split: static host for the console + API elsewhere | Then set `VITE_API_URL` at build time and `CORS_ORIGINS` on the API |
