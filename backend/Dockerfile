# Single-image deploy: the console is built and served by the API process, so
# the whole system is one URL with no CORS and no build-time dependency on
# knowing the API's address.

# --- Stage 1: build the console -------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Same origin, so the client calls relative paths.
ENV VITE_API_URL=""
RUN npm run build

# --- Stage 2: python dependencies -----------------------------------------
FROM python:3.12-slim AS deps
WORKDIR /build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 3: runtime ------------------------------------------------------
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=deps /install /usr/local
COPY --chown=app:app backend/ .
COPY --from=frontend --chown=app:app /ui/dist ./app/static

USER app

# Defaults to the in-process graph: the container serves a complete, correct
# report with no database and no LLM credentials attached.
ENV GRAPH_BACKEND=memory \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
