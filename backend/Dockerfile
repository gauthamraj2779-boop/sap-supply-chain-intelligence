# Backend image. Multi-stage so the runtime layer carries no build toolchain.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

# Run as a non-root user: the container has no reason to hold root.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app . .

USER app

# The graph backend defaults to the in-process store, so the container serves a
# complete, correct report with no database and no LLM credentials attached.
ENV GRAPH_BACKEND=memory \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
