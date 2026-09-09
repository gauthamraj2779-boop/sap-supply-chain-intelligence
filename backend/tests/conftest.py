import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engines.avoidance import find_actions          # noqa: E402
from app.engines.deterministic import run_traversal      # noqa: E402
from app.engines.financial import compute_exposure       # noqa: E402
from app.graph.backends.memory import MemoryBackend      # noqa: E402

# The planted scenario, from data/synthetic/generate_sap_data.py
APEX = "0000001000"       # sole-source villain
NOVA = "0000001001"       # approved alternate source
TOSHIRO = "0000001002"    # contrast: deeply stocked
DELAY = 14


@pytest.fixture(scope="session")
def backend():
    b = MemoryBackend()
    b.connect()
    yield b
    b.close()


@pytest.fixture(scope="session")
def traversal(backend):
    return run_traversal(backend, APEX, DELAY)


@pytest.fixture(scope="session")
def exposure(traversal, backend):
    return compute_exposure(traversal, backend)


@pytest.fixture(scope="session")
def plan(backend, traversal, exposure):
    return find_actions(backend, traversal, exposure)
