"""Generate an SAP-faithful synthetic dataset.

Field names are real SAP DDIC names (LFA1.LIFNR, EKPO.NETWR, EKET.EINDT,
RESB.BDMNG, MARD.LABST, VBAP.NETWR, LIKP.LFDAT ...) so the graph, the ontology
and the lineage trails all reference genuine SAP semantics.

The dataset is deliberately *authored*, not randomised, because the demo depends
on three planted conditions:

  1. Apex Microelectronics (LIFNR 0000001000) is the SOLE primary source for
     MCU-32 and PWR-IC-7, both of which feed near-term aerospace deliveries,
     and both carry thin stock at plant 1010. -> large blast radius.
  2. Nova Components (0000001001) is an approved ALTERNATE source for MCU-32
     with a 4-day lead time. -> the avoidance engine can find a real rescue.
     Plant 1020 holds transferable MCU-32 safety stock. -> second rescue.
     Production order 9003 carries slack. -> third rescue (re-sequencing).
  3. Toshiro Metals (0000001002) supplies well-stocked materials with long
     coverage. -> the CONTRAST case: the system must report low impact and
     not simply alarm on every supplier.
  4. Manufacturing is multi-level: FCB-100 (a sub-assembly built at 1010) is a
     component of FMS-850, so a raw-material shortfall reaches the finished
     good through the BOM rather than stopping at the sub-assembly's order.

Run:  python -m data.synthetic.generate_sap_data
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

# All dates are generated relative to this anchor so the demo always looks
# current, while tests assert on day offsets rather than absolute dates.
AS_OF = date.today()


def d(offset: int) -> str:
    return (AS_OF + timedelta(days=offset)).isoformat()


# ==========================================================================
# T001W -- Plants
# ==========================================================================
# NOTE ON idle_plant_cost_per_day: SAP has no such field. It is a management
# accounting figure (fixed overhead + labour absorbed per idle day). It is
# stored here explicitly, per plant, so every dollar of "production halt cost"
# can be traced to a stated assumption rather than a hidden constant.
PLANTS = [
    {
        "WERKS": "1010", "NAME1": "Detroit Avionics Plant", "LAND1": "US",
        "ORT01": "Detroit", "idle_plant_cost_per_day": 180_000.0,
        "_assumption": "idle_plant_cost_per_day is a management accounting input, not an SAP field",
    },
    {
        "WERKS": "1020", "NAME1": "Singapore Systems Plant", "LAND1": "SG",
        "ORT01": "Singapore", "idle_plant_cost_per_day": 145_000.0,
        "_assumption": "idle_plant_cost_per_day is a management accounting input, not an SAP field",
    },
    {
        "WERKS": "1030", "NAME1": "Hamburg Structures Plant", "LAND1": "DE",
        "ORT01": "Hamburg", "idle_plant_cost_per_day": 210_000.0,
        "_assumption": "idle_plant_cost_per_day is a management accounting input, not an SAP field",
    },
]

# ==========================================================================
# LFA1 -- Supplier master
# ==========================================================================
SUPPLIERS = [
    {"LIFNR": "0000001000", "NAME1": "Apex Microelectronics", "LAND1": "TW",
     "ORT01": "Hsinchu", "risk_score": 0.82, "_role": "sole-source villain"},
    {"LIFNR": "0000001001", "NAME1": "Nova Components GmbH", "LAND1": "DE",
     "ORT01": "Dresden", "risk_score": 0.21, "_role": "alternate source"},
    {"LIFNR": "0000001002", "NAME1": "Toshiro Metals K.K.", "LAND1": "JP",
     "ORT01": "Nagoya", "risk_score": 0.18, "_role": "contrast: well stocked"},
    {"LIFNR": "0000001003", "NAME1": "Continental Fasteners Inc", "LAND1": "US",
     "ORT01": "Cleveland", "risk_score": 0.34, "_role": "filler"},
    {"LIFNR": "0000001004", "NAME1": "Meridian Polymers LLC", "LAND1": "US",
     "ORT01": "Akron", "risk_score": 0.29, "_role": "filler"},
]

# ==========================================================================
# KNA1 -- Customer master
# ==========================================================================
CUSTOMERS = [
    {"KUNNR": "0000002001", "NAME1": "Boeing Commercial", "LAND1": "US", "ORT01": "Everett"},
    {"KUNNR": "0000002002", "NAME1": "Airbus SAS", "LAND1": "FR", "ORT01": "Toulouse"},
    {"KUNNR": "0000002003", "NAME1": "Lockheed Martin Aero", "LAND1": "US", "ORT01": "Fort Worth"},
    {"KUNNR": "0000002004", "NAME1": "Embraer S.A.", "LAND1": "BR", "ORT01": "Sao Jose dos Campos"},
    {"KUNNR": "0000002005", "NAME1": "Bombardier Aviation", "LAND1": "CA", "ORT01": "Montreal"},
    {"KUNNR": "0000002006", "NAME1": "Gulfstream Aerospace", "LAND1": "US", "ORT01": "Savannah"},
]

# ==========================================================================
# MARA -- Material master (general).  MTART: ROH=raw, HALB=semi, FERT=finished
# ==========================================================================
MATERIALS = [
    # --- purchased components (ROH) ---
    {"MATNR": "MCU-32",      "MAKTX": "Microcontroller Unit 32-bit",   "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 120.0},
    {"MATNR": "PWR-IC-7",    "MAKTX": "Power Management IC",           "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 85.0},
    {"MATNR": "CAP-TANT-22", "MAKTX": "Tantalum Capacitor 22uF",       "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 9.0},
    {"MATNR": "TI-ALLOY-6",  "MAKTX": "Titanium Alloy Billet Grade 6", "MTART": "ROH",  "MATKL": "METL", "MEINS": "KG", "unit_cost": 2400.0},
    {"MATNR": "FAST-M8",     "MAKTX": "Fastener Set M8 Aerospace",     "MTART": "ROH",  "MATKL": "MECH", "MEINS": "EA", "unit_cost": 18.0},
    {"MATNR": "SEAL-PLY-4",  "MAKTX": "Polymer Seal Ring",             "MTART": "ROH",  "MATKL": "POLY", "MEINS": "EA", "unit_cost": 32.0},
    {"MATNR": "CONN-D38",    "MAKTX": "Connector D38999 Circular",     "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 145.0},
    {"MATNR": "WIRE-HARN-2", "MAKTX": "Wire Harness Assembly",         "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 610.0},
    {"MATNR": "SENS-ACC-3",  "MAKTX": "Accelerometer Sensor 3-Axis",   "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 340.0},
    {"MATNR": "DISP-LCD-8",  "MAKTX": "LCD Display Module 8in",        "MTART": "ROH",  "MATKL": "ELEC", "MEINS": "EA", "unit_cost": 520.0},
    # --- semi-finished (HALB) ---
    {"MATNR": "FCB-100",     "MAKTX": "Flight Control Board",          "MTART": "HALB", "MATKL": "ASSY", "MEINS": "EA", "unit_cost": 3100.0},
    {"MATNR": "PSU-220",     "MAKTX": "Power Supply Unit 220",         "MTART": "HALB", "MATKL": "ASSY", "MEINS": "EA", "unit_cost": 1850.0},
    {"MATNR": "SENSOR-ARR-4","MAKTX": "Sensor Array 4-Channel",        "MTART": "HALB", "MATKL": "ASSY", "MEINS": "EA", "unit_cost": 2250.0},
    # --- finished goods (FERT) ---
    {"MATNR": "ACU-500",     "MAKTX": "Avionics Control Unit 500",     "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 118_000.0},
    {"MATNR": "CSM-300",     "MAKTX": "Cabin Systems Module 300",      "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 96_000.0},
    {"MATNR": "NAV-700",     "MAKTX": "Navigation Computer 700",       "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 142_000.0},
    {"MATNR": "LDG-900",     "MAKTX": "Landing Gear Controller 900",   "MTART": "FERT", "MATKL": "MECH", "MEINS": "EA", "unit_cost": 205_000.0},
    {"MATNR": "ECS-400",     "MAKTX": "Environmental Control System",  "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 174_000.0},
    {"MATNR": "FMS-850",     "MAKTX": "Flight Management System 850",  "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 268_000.0},
    {"MATNR": "APU-600",     "MAKTX": "Auxiliary Power Controller",    "MTART": "FERT", "MATKL": "AVIO", "MEINS": "EA", "unit_cost": 88_000.0},
]

# ==========================================================================
# MARC / MARD -- material per plant / per storage location
#   MARC.DISPO = MRP controller, MARC.PLIFZ = planned delivery time (days)
#   MARC.EISBE = safety stock, MARD.LABST = unrestricted-use stock
# ==========================================================================
# (MATNR, WERKS, LABST unrestricted stock, EISBE safety stock, PLIFZ lead time)
_STOCK = [
    # PLANTED: thin stock on the two Apex sole-source materials at 1010
    ("MCU-32",       "1010",  850.0,  500.0, 21),
    ("PWR-IC-7",     "1010",  400.0,  300.0, 21),
    # PLANTED: transferable MCU-32 safety stock at Singapore, no local demand
    ("MCU-32",       "1020",  800.0,  200.0, 21),
    ("PWR-IC-7",     "1020",  300.0,  250.0, 21),
    ("CAP-TANT-22",  "1010", 5000.0, 1000.0, 14),
    # CONTRAST: Toshiro materials are deeply stocked
    ("TI-ALLOY-6",   "1030", 4200.0,  800.0, 30),
    ("SENS-ACC-3",   "1010", 3600.0,  600.0, 25),
    ("FAST-M8",      "1030",12000.0, 2000.0, 10),
    ("SEAL-PLY-4",   "1030", 6500.0, 1200.0, 12),
    ("SEAL-PLY-4",   "1010", 2200.0,  500.0, 12),
    ("CONN-D38",     "1010", 1800.0,  400.0, 18),
    ("WIRE-HARN-2",  "1030",  900.0,  200.0, 20),
    ("DISP-LCD-8",   "1020",  700.0,  150.0, 24),
    # produced materials carry modest finished stock
    ("FCB-100",      "1010",   40.0,   10.0,  0),
    ("PSU-220",      "1020",   35.0,   10.0,  0),
    ("SENSOR-ARR-4", "1010",   25.0,    5.0,  0),
    ("ACU-500",      "1010",    8.0,    2.0,  0),
    ("CSM-300",      "1010",    6.0,    2.0,  0),
    ("NAV-700",      "1020",    5.0,    1.0,  0),
    ("LDG-900",      "1030",    4.0,    1.0,  0),
    ("ECS-400",      "1030",    7.0,    2.0,  0),
    ("FMS-850",      "1010",    3.0,    1.0,  0),
    ("APU-600",      "1020",    9.0,    2.0,  0),
]

# ==========================================================================
# EINA / EINE -- purchasing info records ("who CAN supply what")
#   This is the table the avoidance engine mines for alternate sources.
# ==========================================================================
# (MATNR, LIFNR, NETPR info price, APLFZ lead time days, is_primary)
_SOURCE_LIST = [
    ("MCU-32",       "0000001000", 120.00, 21, True),   # Apex   -- primary
    ("MCU-32",       "0000001001", 122.52,  4, False),  # Nova   -- ALTERNATE (+2.1%)
    ("PWR-IC-7",     "0000001000",  85.00, 21, True),   # Apex   -- SOLE source
    ("CAP-TANT-22",  "0000001000",   9.00, 14, True),
    ("CAP-TANT-22",  "0000001001",   9.45,  6, False),  # alternate
    ("TI-ALLOY-6",   "0000001002",2400.00, 30, True),
    ("SENS-ACC-3",   "0000001002", 340.00, 25, True),
    ("DISP-LCD-8",   "0000001001", 520.00, 24, True),
    ("FAST-M8",      "0000001003",  18.00, 10, True),
    ("CONN-D38",     "0000001003", 145.00, 18, True),
    ("SEAL-PLY-4",   "0000001004",  32.00, 12, True),
    ("WIRE-HARN-2",  "0000001004", 610.00, 20, True),
]

# ==========================================================================
# EKKO / EKPO / EKET -- purchase orders, items, schedule lines
# ==========================================================================
# (EBELN, LIFNR, [(EBELP, MATNR, WERKS, MENGE, EINDT offset)])
_PURCHASE_ORDERS = [
    ("4500012", "0000001000", [("10", "MCU-32",      "1010", 2500.0,  6),
                               ("20", "PWR-IC-7",    "1010", 1500.0,  7)]),
    ("4500015", "0000001000", [("10", "PWR-IC-7",    "1020",  900.0,  9)]),
    ("4500018", "0000001000", [("10", "CAP-TANT-22", "1010", 8000.0,  5)]),
    ("4500021", "0000001001", [("10", "DISP-LCD-8",  "1020",  400.0, 11)]),
    ("4500024", "0000001002", [("10", "TI-ALLOY-6",  "1030", 1200.0,  8),
                               ("20", "SENS-ACC-3",  "1010",  800.0, 10)]),
    ("4500027", "0000001003", [("10", "FAST-M8",     "1030", 5000.0,  4),
                               ("20", "CONN-D38",    "1010",  900.0,  6)]),
    ("4500030", "0000001004", [("10", "SEAL-PLY-4",  "1030", 3000.0,  7),
                               ("20", "WIRE-HARN-2", "1030",  500.0,  9)]),
    ("4500033", "0000001002", [("10", "TI-ALLOY-6",  "1030",  600.0, 16)]),
    ("4500036", "0000001003", [("10", "FAST-M8",     "1030", 4000.0, 19)]),
    ("4500039", "0000001004", [("10", "SEAL-PLY-4",  "1010", 1500.0, 13)]),
    ("4500042", "0000001001", [("10", "CAP-TANT-22", "1010", 3000.0, 22)]),
    ("4500045", "0000001002", [("10", "SENS-ACC-3",  "1010",  400.0, 26)]),
    ("4500048", "0000001003", [("10", "CONN-D38",    "1010",  600.0, 24)]),
    ("4500051", "0000001004", [("10", "WIRE-HARN-2", "1030",  300.0, 28)]),
    ("4500054", "0000001001", [("10", "DISP-LCD-8",  "1020",  200.0, 30)]),
]

# ==========================================================================
# MAST / STKO / STPO -- bills of material
# ==========================================================================
# MAST links a material at a plant to a BOM number; STKO is the BOM header and
# carries BMENG, the base quantity the component quantities are stated against;
# STPO holds the components. The base quantity lives on STKO because that is
# where SAP keeps it -- inventing a BMENG field on MAST would be a lie about the
# DDIC, and without it a component such as "16.67 MCU-32 per ACU-500" could only
# be written as a repeating fraction.
#
# The finished goods (FERT) draw on the sub-assemblies (HALB) as well as on raw
# stock; the sub-assemblies draw only on raw (ROH) components. FCB-100 feeding
# FMS-850 is the edge the whole multi-level cascade runs through.
#
# (parent MATNR, WERKS, STLNR bom number, BMENG base quantity,
#  [(component IDNRK, MENGE per base quantity)])
_BOMS = [
    # --- finished goods (FERT) ---
    ("ACU-500",      "1010", "00010001", 6,
     [("SENSOR-ARR-4", 6), ("MCU-32", 100), ("CAP-TANT-22", 240), ("CONN-D38", 24)]),
    ("CSM-300",      "1010", "00010002", 1,
     [("SENSOR-ARR-4", 1), ("MCU-32", 10), ("SEAL-PLY-4", 8)]),
    ("NAV-700",      "1020", "00010003", 3,
     [("PWR-IC-7", 25), ("DISP-LCD-8", 6)]),
    ("LDG-900",      "1030", "00010004", 1,
     [("TI-ALLOY-6", 16), ("FAST-M8", 40)]),
    ("ECS-400",      "1030", "00010005", 1,
     [("SEAL-PLY-4", 16), ("WIRE-HARN-2", 5)]),
    ("FMS-850",      "1010", "00010006", 1,
     [("FCB-100", 4), ("SENSOR-ARR-4", 1), ("SENS-ACC-3", 8), ("CONN-D38", 4)]),
    ("APU-600",      "1020", "00010007", 1,
     [("PSU-220", 1), ("CAP-TANT-22", 16)]),
    # --- sub-assemblies (HALB): raw components only ---
    ("FCB-100",      "1010", "00010008", 2,
     [("MCU-32", 9), ("PWR-IC-7", 6), ("CONN-D38", 2)]),
    ("PSU-220",      "1020", "00010009", 3,
     [("PWR-IC-7", 14)]),
    ("SENSOR-ARR-4", "1010", "00010010", 1,
     [("SENS-ACC-3", 2), ("CONN-D38", 1)]),
]

# ==========================================================================
# AFKO / AFPO / RESB -- production orders and their component requirements
# ==========================================================================
# Component *quantities* are not listed here: RESB is exploded from the BOM
# above the way SAP derives it when an order is created, so the reservations
# cannot drift away from the bill of material. What an order does carry is
# scheduling -- when each component is needed -- which is not BOM data.
#
# (AUFNR, output MATNR, WERKS, GAMNG qty, GSTRP start off, GLTRP finish off,
#  {component MATNR: BDTER need-date off})
_PRODUCTION_ORDERS = [
    ("000009001", "ACU-500", "1010", 120.0,  4, 18,
     {"SENSOR-ARR-4": 8, "MCU-32": 8, "CAP-TANT-22": 8, "CONN-D38": 9}),
    ("000009002", "FCB-100", "1010", 200.0,  5, 15,
     {"MCU-32": 9, "PWR-IC-7": 9, "CONN-D38": 9}),
    ("000009003", "CSM-300", "1010",  80.0,  6, 22,
     {"SENSOR-ARR-4": 10, "MCU-32": 10, "SEAL-PLY-4": 10}),
    ("000009004", "NAV-700", "1020",  60.0,  8, 25,
     {"PWR-IC-7": 12, "DISP-LCD-8": 12}),
    ("000009005", "PSU-220", "1020", 150.0,  7, 20,
     {"PWR-IC-7": 11}),
    ("000009006", "LDG-900", "1030",  40.0, 10, 28,
     {"TI-ALLOY-6": 14, "FAST-M8": 14}),
    ("000009007", "ECS-400", "1030",  55.0, 12, 30,
     {"SEAL-PLY-4": 16, "WIRE-HARN-2": 16}),
    ("000009008", "FMS-850", "1010",  45.0, 14, 35,
     {"FCB-100": 20, "SENSOR-ARR-4": 20, "SENS-ACC-3": 20, "CONN-D38": 20}),
    # Feeds the sensor arrays the three 1010 finished goods consume: without it
    # SENSOR-ARR-4 demand (245) would exceed the 25 units on the shelf.
    ("000009009", "SENSOR-ARR-4", "1010", 220.0,  1,  7,
     {"SENS-ACC-3": 3, "CONN-D38": 3}),
]

# ==========================================================================
# VBAK / VBAP -- sales orders.  LIKP / LIPS -- outbound deliveries.
# ==========================================================================
# (VBELN, KUNNR, [(POSNR, MATNR, WERKS, KWMENG, NETWR)], AUDAT off)
_SALES_ORDERS = [
    ("0004502", "0000002001", [("10", "ACU-500", "1010", 120.0, 31_200_000.0)], -30),
    ("0004508", "0000002002", [("10", "CSM-300", "1010",  80.0, 18_700_000.0)], -28),
    ("0004511", "0000002003", [("10", "NAV-700", "1020",  60.0, 12_400_000.0)], -25),
    ("0004514", "0000002004", [("10", "LDG-900", "1030",  40.0,  9_800_000.0)], -22),
    ("0004517", "0000002005", [("10", "ECS-400", "1030",  55.0, 11_300_000.0)], -20),
    ("0004520", "0000002006", [("10", "FMS-850", "1010",  45.0, 14_600_000.0)], -18),
    ("0004523", "0000002001", [("10", "APU-600", "1020",  70.0,  7_200_000.0)], -16),
    ("0004526", "0000002002", [("10", "ACU-500", "1010",  40.0, 10_400_000.0)], -14),
    ("0004529", "0000002003", [("10", "CSM-300", "1010",  30.0,  7_000_000.0)], -12),
    ("0004532", "0000002004", [("10", "NAV-700", "1020",  25.0,  5_200_000.0)], -10),
    ("0004535", "0000002005", [("10", "LDG-900", "1030",  20.0,  4_900_000.0)], -8),
    ("0004538", "0000002006", [("10", "ECS-400", "1030",  18.0,  3_700_000.0)], -6),
]

# (VBELN delivery, ref sales order VBELN, KUNNR, WERKS, LFDAT off, penalty rate)
_DELIVERIES = [
    ("0080001", "0004502", "0000002001", "1010", 20, 0.08),
    ("0080002", "0004508", "0000002002", "1010", 24, 0.08),
    ("0080003", "0004511", "0000002003", "1020", 27, 0.06),
    ("0080004", "0004514", "0000002004", "1030", 30, 0.05),
    ("0080005", "0004517", "0000002005", "1030", 32, 0.05),
    ("0080006", "0004520", "0000002006", "1010", 37, 0.07),
    ("0080007", "0004523", "0000002001", "1020", 34, 0.06),
    ("0080008", "0004526", "0000002002", "1010", 26, 0.08),
    ("0080009", "0004529", "0000002003", "1010", 29, 0.06),
    ("0080010", "0004532", "0000002004", "1020", 31, 0.05),
]


def build() -> dict[str, list[dict]]:
    cost = {m["MATNR"]: m["unit_cost"] for m in MATERIALS}
    name = {m["MATNR"]: m["MAKTX"] for m in MATERIALS}
    uom = {m["MATNR"]: m["MEINS"] for m in MATERIALS}

    marc, mard = [], []
    for matnr, werks, labst, eisbe, plifz in _STOCK:
        marc.append({
            "MATNR": matnr, "WERKS": werks, "DISPO": f"{werks[:3]}",
            "PLIFZ": plifz, "EISBE": eisbe,
            "BESKZ": "F" if plifz > 0 else "E",  # F=external, E=in-house
        })
        mard.append({
            "MATNR": matnr, "WERKS": werks, "LGORT": "0001", "LABST": labst,
        })

    source_list = [
        {"MATNR": m, "LIFNR": l, "NETPR": p, "APLFZ": lt, "is_primary": prim,
         "unit_cost": cost[m]}
        for m, l, p, lt, prim in _SOURCE_LIST
    ]

    ekko, ekpo, eket = [], [], []
    for ebeln, lifnr, items in _PURCHASE_ORDERS:
        ekko.append({"EBELN": ebeln, "LIFNR": lifnr, "BUKRS": "1000",
                     "BEDAT": d(-35), "BSART": "NB", "WAERS": "USD"})
        for ebelp, matnr, werks, menge, eindt_off in items:
            netwr = round(menge * cost[matnr], 2)
            ekpo.append({
                "EBELN": ebeln, "EBELP": ebelp, "MATNR": matnr, "TXZ01": name[matnr],
                "WERKS": werks, "MENGE": menge, "MEINS": "EA",
                "NETPR": cost[matnr], "NETWR": netwr, "ELIKZ": "",
            })
            eket.append({
                "EBELN": ebeln, "EBELP": ebelp, "ETENR": "0001",
                "EINDT": d(eindt_off), "MENGE": menge, "WEMNG": 0.0,
            })

    mast, stko, stpo = [], [], []
    bom_of: dict[str, tuple[float, list[tuple[str, float]]]] = {}
    for parent, werks, stlnr, bmeng, comps in _BOMS:
        mast.append({"MATNR": parent, "WERKS": werks, "STLAN": "1",
                     "STLNR": stlnr, "STLAL": "01", "STLTY": "M"})
        stko.append({"STLNR": stlnr, "STLAL": "01", "STLTY": "M",
                     "BMENG": float(bmeng), "BMEIN": uom[parent], "STLST": "01"})
        for i, (idnrk, menge) in enumerate(comps, start=1):
            stpo.append({
                "STLNR": stlnr, "STLAL": "01", "STLKN": f"{i:08d}",
                "POSNR": f"{i * 10:04d}", "IDNRK": idnrk, "MENGE": float(menge),
                "MEINS": uom[idnrk], "POSTP": "L",
            })
        bom_of[parent] = (float(bmeng), [(c, float(q)) for c, q in comps])

    afko, afpo, resb = [], [], []
    rsnum = 1000
    for aufnr, out_matnr, werks, gamng, gstrp, gltrp, need_by in _PRODUCTION_ORDERS:
        afko.append({"AUFNR": aufnr, "PLNBEZ": out_matnr, "GAMNG": gamng,
                     "GSTRP": d(gstrp), "GLTRP": d(gltrp), "WERKS": werks})
        afpo.append({"AUFNR": aufnr, "POSNR": "0001", "MATNR": out_matnr,
                     "PSMNG": gamng, "WERKS": werks})
        bmeng, comps = bom_of[out_matnr]
        # An order that schedules a component the BOM does not contain (or omits
        # one it does) is an authoring slip, not a data condition worth shipping.
        if {c for c, _ in comps} != set(need_by):
            raise ValueError(
                f"Order {aufnr} schedules {sorted(need_by)} but the {out_matnr} "
                f"BOM lists {sorted(c for c, _ in comps)}"
            )
        rsnum += 1
        factor = gamng / bmeng
        for i, (c_matnr, per_base) in enumerate(comps, start=1):
            resb.append({
                "RSNUM": str(rsnum), "RSPOS": f"{i:04d}", "AUFNR": aufnr,
                "MATNR": c_matnr, "WERKS": werks,
                "BDMNG": round(per_base * factor, 3),
                "BDTER": d(need_by[c_matnr]), "ENMNG": 0.0,
            })

    vbak, vbap = [], []
    for vbeln, kunnr, items, audat_off in _SALES_ORDERS:
        total = sum(i[4] for i in items)
        vbak.append({"VBELN": vbeln, "KUNNR": kunnr, "AUDAT": d(audat_off),
                     "NETWR": total, "WAERK": "USD", "VKORG": "1000"})
        for posnr, matnr, werks, kwmeng, netwr in items:
            vbap.append({"VBELN": vbeln, "POSNR": posnr, "MATNR": matnr,
                         "ARKTX": name[matnr], "WERKS": werks,
                         "KWMENG": kwmeng, "NETWR": netwr})

    likp, lips = [], []
    so_lookup = {v["VBELN"]: v for v in vbak}
    for vbeln, ref_so, kunnr, werks, lfdat_off, penalty in _DELIVERIES:
        likp.append({
            "VBELN": vbeln, "KUNNR": kunnr, "LFDAT": d(lfdat_off),
            "WADAT": d(lfdat_off), "VSTEL": werks, "LFART": "LF",
            "penalty_rate": penalty,
            "_assumption": "penalty_rate is a contract term, held outside SAP core tables",
        })
        for item in (i for i in vbap if i["VBELN"] == ref_so):
            lips.append({
                "VBELN": vbeln, "POSNR": item["POSNR"], "MATNR": item["MATNR"],
                "WERKS": item["WERKS"], "LFIMG": item["KWMENG"],
                "VGBEL": ref_so, "VGPOS": item["POSNR"],
                "NETWR": item["NETWR"],
            })
        _ = so_lookup.get(ref_so)

    return {
        "plants": PLANTS,
        "suppliers": SUPPLIERS,
        "customers": CUSTOMERS,
        "materials": MATERIALS,
        "material_plant": marc,
        "material_stock": mard,
        "source_list": source_list,
        "po_header": ekko,
        "po_item": ekpo,
        "po_schedule": eket,
        "bom_link": mast,
        "bom_header": stko,
        "bom_item": stpo,
        "prod_order_header": afko,
        "prod_order_item": afpo,
        "reservations": resb,
        "so_header": vbak,
        "so_item": vbap,
        "delivery_header": likp,
        "delivery_item": lips,
    }


TABLE_MAP = {
    "plants": "T001W", "suppliers": "LFA1", "customers": "KNA1",
    "materials": "MARA", "material_plant": "MARC", "material_stock": "MARD",
    "source_list": "EINA/EINE", "po_header": "EKKO", "po_item": "EKPO",
    "po_schedule": "EKET", "bom_link": "MAST", "bom_header": "STKO",
    "bom_item": "STPO", "prod_order_header": "AFKO",
    "prod_order_item": "AFPO", "reservations": "RESB",
    "so_header": "VBAK", "so_item": "VBAP",
    "delivery_header": "LIKP", "delivery_item": "LIPS",
}


def write(out_dir: Path = OUT_DIR) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = build()
    counts = {}
    for key, rows in dataset.items():
        (out_dir / f"{key}.json").write_text(json.dumps(rows, indent=2))
        counts[key] = len(rows)

    (out_dir / "meta.json").write_text(json.dumps({
        "as_of": AS_OF.isoformat(),
        "table_map": TABLE_MAP,
        "counts": counts,
        "provenance": "SYNTHETIC -- SAP-structured. Real DDIC table and field "
                      "names; values authored for demonstration. No real "
                      "customer or supplier data.",
        "planted_scenario": {
            "villain_supplier": "0000001000",
            "sole_source_materials": ["MCU-32", "PWR-IC-7"],
            "alternate_supplier": "0000001001",
            "transferable_stock_plant": "1020",
            "slack_production_order": "000009003",
            "contrast_supplier": "0000001002",
            "multi_level_bom": {
                "sub_assembly": "FCB-100",
                "built_by": "000009002",
                "assembles_into": "FMS-850",
                "consumed_by": "000009008",
            },
        },
    }, indent=2))
    return counts


if __name__ == "__main__":
    c = write()
    total = sum(c.values())
    for k in sorted(c):
        print(f"  {TABLE_MAP[k]:<12} {k:<20} {c[k]:>5}")
    print(f"  {'':<12} {'TOTAL':<20} {total:>5} records")
