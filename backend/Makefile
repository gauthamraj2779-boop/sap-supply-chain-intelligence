VENV := venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: help setup data ontology load test run clean check

help:
	@echo "SAP Knowledge Graph - backend"
	@echo ""
	@echo "  make setup     create venv (Python 3.12) and install dependencies"
	@echo "  make data      generate the SAP-faithful synthetic dataset"
	@echo "  make ontology  emit the OWL ontology + SHACL shapes"
	@echo "  make test      run the full test suite"
	@echo "  make run       start the API on http://localhost:8000 (docs at /docs)"
	@echo "  make check     end-to-end smoke test against a live server"
	@echo "  make load      load the graph into Neo4j (needs NEO4J_* in .env)"
	@echo ""
	@echo "No credentials are required for setup/data/ontology/test/run/check."

setup:
	/opt/homebrew/bin/python3.12 -m venv $(VENV) 2>/dev/null || python3.12 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Setup complete. Next: make data && make test && make run"

data:
	$(PY) -m data.synthetic.generate_sap_data

ontology:
	$(PY) -m app.graph.ontology

test:
	$(PY) -m pytest tests/ -q

run:
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

load:
	$(PY) -m app.graph.loader

check:
	$(PY) scripts/smoke_test.py

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__
