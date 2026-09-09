"""Missing-value estimation.

The shipped dataset is complete, so this path never fires on the demo data --
which is exactly why it needs its own tests. The records below are constructed
here rather than by corrupting data/synthetic: the gap is the fixture.
"""

import json
import shutil

from app.config import DATA_DIR
from app.engines.estimation import find_estimates, from_traversal
from app.engines.orchestrator import analyse
from app.graph.backends.memory import MemoryBackend
from app.validation.confidence import compute_confidence
from tests.conftest import APEX, DELAY

# Four priced ELEC purchase order lines at 120, 85, 9 and 145 per unit, plus one
# line whose NETWR never made it into the extract. Mean of the four is 89.75.
PO_ITEMS = [
    {"EBELN": "4500009001", "EBELP": "00010", "MATNR": "MCU-32",
     "MENGE": 500.0, "NETWR": 60_000.0},
    {"EBELN": "4500009001", "EBELP": "00020", "MATNR": "PWR-IC-7",
     "MENGE": 400.0, "NETWR": 34_000.0},
    {"EBELN": "4500009002", "EBELP": "00010", "MATNR": "CAP-TANT-22",
     "MENGE": 1_000.0, "NETWR": 9_000.0},
    {"EBELN": "4500009002", "EBELP": "00020", "MATNR": "CONN-D38",
     "MENGE": 200.0, "NETWR": 29_000.0},
    {"EBELN": "4500009003", "EBELP": "00010", "MATNR": "SENS-ACC-3",
     "MENGE": 100.0, "NETWR": 0.0},
]

MATERIALS = [
    {"MATNR": "MCU-32", "MATKL": "ELEC", "unit_cost": 120.0},
    {"MATNR": "PWR-IC-7", "MATKL": "ELEC", "unit_cost": 85.0},
    {"MATNR": "CAP-TANT-22", "MATKL": "ELEC", "unit_cost": 9.0},
    {"MATNR": "CONN-D38", "MATKL": "ELEC", "unit_cost": 145.0},
    {"MATNR": "SENS-ACC-3", "MATKL": "ELEC", "unit_cost": 340.0},
]


def test_missing_netwr_is_estimated_from_its_material_group():
    result = find_estimates(PO_ITEMS, [], MATERIALS)

    assert len(result.estimates) == 1
    est = result.estimates[0]
    assert est.entity == "PurchaseOrderItem"
    assert est.key == "EBELN=4500009003/EBELP=00010"
    assert est.sap_field == "EKPO.NETWR"
    # 89.75 mean net value per unit across the four ELEC lines x 100 units.
    assert est.estimated_value == 8_975.00
    assert est.sample_size == 4
    assert "MATKL=ELEC" in est.basis
    assert "89.75" in est.basis
    assert est.is_estimated is True


def test_the_estimate_is_declared_as_an_assumption():
    result = find_estimates(PO_ITEMS, [], MATERIALS)
    text = " ".join(result.assumptions)
    assert "1 of 10 line item(s)" in text
    assert "estimated" in text


def test_a_priced_sibling_line_beats_the_group_mean():
    """Same-material evidence is stronger than same-group evidence."""
    items = PO_ITEMS + [
        {"EBELN": "4500009004", "EBELP": "00010", "MATNR": "SENS-ACC-3",
         "MENGE": 50.0, "NETWR": 15_000.0},
    ]
    est = find_estimates(items, [], MATERIALS).estimates[0]
    assert "MATNR=SENS-ACC-3" in est.basis
    assert est.sample_size == 1
    assert est.estimated_value == 30_000.00  # 300.00/unit x 100


def test_unit_cost_times_quantity_when_no_comparable_line_exists():
    lone = [{"EBELN": "4500009005", "EBELP": "00010", "MATNR": "TI-ALLOY-6",
             "MENGE": 12.0, "NETWR": None}]
    materials = [{"MATNR": "TI-ALLOY-6", "MATKL": "METL", "unit_cost": 2_400.0}]
    est = find_estimates(lone, [], materials).estimates[0]
    assert est.estimated_value == 28_800.00
    assert "MARA unit cost" in est.basis
    assert est.sample_size == 1


def test_missing_sales_order_value_uses_kwmeng():
    so_items = [
        {"VBELN": "0000009001", "POSNR": "000010", "MATNR": "ACU-500",
         "KWMENG": 10.0, "NETWR": 1_500_000.0},
        {"VBELN": "0000009002", "POSNR": "000010", "MATNR": "ACU-500",
         "KWMENG": 4.0, "NETWR": 0.0},
    ]
    materials = [{"MATNR": "ACU-500", "MATKL": "AVIO", "unit_cost": 118_000.0}]
    est = find_estimates([], so_items, materials).estimates[0]
    assert est.entity == "SalesOrderItem"
    assert est.sap_field == "VBAP.NETWR"
    assert est.estimated_value == 600_000.00  # 150,000/unit x 4


def test_missing_unit_cost_is_estimated_from_the_info_record_price():
    materials = [{"MATNR": "MCU-32", "MATKL": "ELEC", "unit_cost": 0.0}]
    sources = [{"MATNR": "MCU-32", "NETPR": 120.0}, {"MATNR": "MCU-32", "NETPR": 132.0}]
    est = find_estimates([], [], materials, sources).estimates[0]
    assert est.entity == "Material"
    assert est.sap_field == "MARA unit cost"
    assert est.estimated_value == 126.00
    assert est.sample_size == 2
    assert "EINE.NETPR" in est.basis


def test_nothing_is_invented_when_there_is_no_evidence():
    """No quantity, no peer, no cost: the line is reported, not guessed at."""
    orphan = [{"EBELN": "4500009009", "EBELP": "00010", "MATNR": "UNKNOWN-1",
               "MENGE": 0.0, "NETWR": 0.0}]
    result = find_estimates(orphan, [], [{"MATNR": "UNKNOWN-1", "unit_cost": 0.0}])
    assert result.estimates == []
    assert result.unresolved
    assert "could not even be estimated" in " ".join(result.assumptions)


def test_estimated_values_lower_confidence(traversal):
    baseline = compute_confidence(traversal, None, None)
    result = find_estimates(PO_ITEMS, [], MATERIALS)
    lowered = compute_confidence(traversal, None, None, estimation=result)

    assert lowered.data_completeness < baseline.data_completeness
    assert lowered.overall < baseline.overall
    assert "estimated_values" in lowered.degraded_modes
    assert any("estimated value" in n for n in lowered.notes)


def test_the_shipped_dataset_needs_no_estimates(backend, traversal):
    """Every NETWR and unit cost on the demo path is present in the records."""
    result = from_traversal(traversal, backend)
    assert result.line_items_examined > 0
    assert result.estimates == []
    assert result.unresolved == []
    assert result.assumptions == []


def test_a_gap_in_the_extract_surfaces_through_the_whole_report(tmp_path, backend):
    """The doc's fault case, end to end -- on a copy, never on the shipped data."""
    data_dir = tmp_path / "synthetic"
    shutil.copytree(DATA_DIR, data_dir)

    items = json.loads((data_dir / "po_item.json").read_text())
    apex_pos = {h["EBELN"] for h in json.loads((data_dir / "po_header.json").read_text())
                if h["LIFNR"] == APEX}
    target = next(i for i in items if i["EBELN"] in apex_pos)
    target["NETWR"] = 0.0
    (data_dir / "po_item.json").write_text(json.dumps(items))

    gapped = MemoryBackend(data_dir=data_dir)
    gapped.connect()
    try:
        report = analyse(gapped, APEX, DELAY)
    finally:
        gapped.close()

    est = next(e for e in report.estimates
               if e.key == f"EBELN={target['EBELN']}/EBELP={target['EBELP']}")
    assert est.sap_field == "EKPO.NETWR"
    assert est.is_estimated is True
    assert est.estimated_value > 0
    assert est.sample_size >= 1
    assert est.basis

    assert any("estimated" in a for a in report.financial_exposure.assumptions)
    assert "estimated_values" in report.confidence.degraded_modes

    baseline = analyse(backend, APEX, DELAY)
    assert baseline.estimates == []
    assert report.confidence.data_completeness < baseline.confidence.data_completeness
    assert report.confidence.overall < baseline.confidence.overall
