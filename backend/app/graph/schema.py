"""Graph schema: SAP tables -> business ontology nodes and edges.

This module is the single source of truth for the technical->business mapping.
The ontology emitter, the loader, and every lineage trail read from here, so
"which SAP field produced this node property" is never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldMapping:
    sap_table: str
    sap_field: str
    graph_property: str
    business_term: str


@dataclass(frozen=True)
class NodeType:
    label: str
    source_tables: tuple[str, ...]
    key_property: str
    business_definition: str
    fields: tuple[FieldMapping, ...] = field(default_factory=tuple)

    def lineage_for(self, prop: str) -> FieldMapping | None:
        for f in self.fields:
            if f.graph_property == prop:
                return f
        return None


@dataclass(frozen=True)
class EdgeType:
    type: str
    source_label: str
    target_label: str
    derived_from: str
    business_meaning: str
    inferred: bool = False


def _fm(table: str, pairs: list[tuple[str, str, str]]) -> tuple[FieldMapping, ...]:
    return tuple(FieldMapping(table, sap, prop, term) for sap, prop, term in pairs)


NODE_TYPES: dict[str, NodeType] = {
    "Supplier": NodeType(
        "Supplier", ("LFA1",), "lifnr",
        "An external party from which the enterprise procures materials.",
        _fm("LFA1", [("LIFNR", "lifnr", "Supplier Number"),
                     ("NAME1", "name", "Supplier Name"),
                     ("LAND1", "country", "Country Key")]),
    ),
    "Material": NodeType(
        "Material", ("MARA", "MARC", "MARD"), "matnr",
        "A good that is procured, produced, stocked or sold.",
        _fm("MARA", [("MATNR", "matnr", "Material Number"),
                     ("MAKTX", "name", "Material Description"),
                     ("MTART", "material_type", "Material Type")])
        + _fm("MARD", [("LABST", "on_hand", "Unrestricted-Use Stock")])
        + _fm("MARC", [("EISBE", "safety_stock", "Safety Stock"),
                       ("PLIFZ", "lead_time_days", "Planned Delivery Time")]),
    ),
    "Plant": NodeType(
        "Plant", ("T001W",), "werks",
        "An operational unit that produces or stores materials.",
        _fm("T001W", [("WERKS", "werks", "Plant"),
                      ("NAME1", "name", "Plant Name"),
                      ("LAND1", "country", "Country Key")]),
    ),
    "PurchaseOrder": NodeType(
        "PurchaseOrder", ("EKKO", "EKPO"), "po_key",
        "A commitment to buy a material from a supplier.",
        _fm("EKKO", [("EBELN", "ebeln", "Purchasing Document Number"),
                     ("LIFNR", "lifnr", "Supplier Number")])
        + _fm("EKPO", [("EBELP", "ebelp", "Item Number"),
                       ("MATNR", "matnr", "Material Number"),
                       ("MENGE", "menge", "Purchase Order Quantity"),
                       ("NETWR", "net_value", "Net Order Value")]),
    ),
    "ScheduleLine": NodeType(
        "ScheduleLine", ("EKET",), "sched_key",
        "A dated delivery commitment within a purchase order item.",
        _fm("EKET", [("EINDT", "delivery_date", "Item Delivery Date"),
                     ("MENGE", "menge", "Scheduled Quantity")]),
    ),
    "SourceList": NodeType(
        "SourceList", ("EINA", "EINE"), "source_key",
        "An approved supplier-material relationship with price and lead time.",
        _fm("EINA", [("MATNR", "matnr", "Material Number"),
                     ("LIFNR", "lifnr", "Supplier Number")])
        + _fm("EINE", [("NETPR", "net_price", "Net Price"),
                       ("APLFZ", "lead_time_days", "Planned Delivery Time")]),
    ),
    "ProductionOrder": NodeType(
        "ProductionOrder", ("AFKO", "AFPO"), "aufnr",
        "An order to manufacture a quantity of a material by a date.",
        _fm("AFKO", [("AUFNR", "aufnr", "Order Number"),
                     ("PLNBEZ", "output_matnr", "Planned Material"),
                     ("GAMNG", "order_qty", "Total Order Quantity"),
                     ("GLTRP", "scheduled_finish", "Basic Finish Date")]),
    ),
    "Reservation": NodeType(
        "Reservation", ("RESB",), "resb_key",
        "A dated component requirement raised by a production order.",
        _fm("RESB", [("AUFNR", "aufnr", "Order Number"),
                     ("MATNR", "matnr", "Material Number"),
                     ("BDMNG", "required_qty", "Requirement Quantity"),
                     ("BDTER", "required_date", "Requirement Date")]),
    ),
    "SalesOrder": NodeType(
        "SalesOrder", ("VBAK", "VBAP"), "so_key",
        "A customer commitment to buy finished goods.",
        _fm("VBAK", [("VBELN", "vbeln", "Sales Document"),
                     ("KUNNR", "kunnr", "Sold-To Party")])
        + _fm("VBAP", [("POSNR", "posnr", "Sales Document Item"),
                       ("MATNR", "matnr", "Material Number"),
                       ("KWMENG", "order_qty", "Cumulative Order Quantity"),
                       ("NETWR", "net_value", "Net Value of the Order Item")]),
    ),
    "Delivery": NodeType(
        "Delivery", ("LIKP", "LIPS"), "vbeln",
        "A planned outbound shipment fulfilling a sales order.",
        _fm("LIKP", [("VBELN", "vbeln", "Delivery Number"),
                     ("KUNNR", "kunnr", "Ship-To Party"),
                     ("LFDAT", "planned_goods_issue", "Delivery Date")])
        + _fm("LIPS", [("VGBEL", "ref_sales_order", "Reference Document"),
                       ("LFIMG", "delivery_qty", "Actual Quantity Delivered")]),
    ),
    "Customer": NodeType(
        "Customer", ("KNA1",), "kunnr",
        "A party to which finished goods are sold and shipped.",
        _fm("KNA1", [("KUNNR", "kunnr", "Customer Number"),
                     ("NAME1", "name", "Customer Name"),
                     ("LAND1", "country", "Country Key")]),
    ),
}

EDGE_TYPES: tuple[EdgeType, ...] = (
    EdgeType("SUPPLIES", "Supplier", "Material", "EINA.LIFNR -> LFA1.LIFNR",
             "Supplier is an approved source for this material"),
    EdgeType("FULFILLS", "Supplier", "PurchaseOrder", "EKKO.LIFNR -> LFA1.LIFNR",
             "Supplier is the vendor on this purchase order"),
    EdgeType("ORDERS", "PurchaseOrder", "Material", "EKPO.MATNR -> MARA.MATNR",
             "Purchase order line procures this material"),
    EdgeType("SCHEDULED_AT", "PurchaseOrder", "ScheduleLine",
             "EKET.EBELN+EBELP -> EKPO.EBELN+EBELP",
             "Delivery schedule for the purchase order item"),
    EdgeType("DELIVERED_TO", "PurchaseOrder", "Plant", "EKPO.WERKS -> T001W.WERKS",
             "Receiving plant for the purchase order item"),
    EdgeType("STOCKED_AT", "Material", "Plant", "MARD.WERKS -> T001W.WERKS",
             "Material carries stock at this plant"),
    EdgeType("PRODUCES", "ProductionOrder", "Material", "AFPO.MATNR -> MARA.MATNR",
             "Production order manufactures this material"),
    EdgeType("REQUIRES", "ProductionOrder", "Reservation", "RESB.AUFNR -> AFKO.AUFNR",
             "Production order raises this component requirement"),
    EdgeType("CONSUMES", "Reservation", "Material", "RESB.MATNR -> MARA.MATNR",
             "Requirement consumes this material"),
    EdgeType("RUNS_AT", "ProductionOrder", "Plant", "AFKO.WERKS -> T001W.WERKS",
             "Plant executing the production order"),
    EdgeType("SOLD_TO", "SalesOrder", "Customer", "VBAK.KUNNR -> KNA1.KUNNR",
             "Customer that placed the sales order"),
    EdgeType("DEMANDS", "SalesOrder", "Material", "VBAP.MATNR -> MARA.MATNR",
             "Sales order line demands this finished material"),
    EdgeType("FULFILLS_ORDER", "Delivery", "SalesOrder", "LIPS.VGBEL -> VBAK.VBELN",
             "Delivery fulfils this sales order", inferred=True),
    EdgeType("SHIPS_FROM", "Delivery", "Plant", "LIKP.VSTEL -> T001W.WERKS",
             "Shipping point plant for the delivery"),
    EdgeType("SHIPS_TO", "Delivery", "Customer", "LIKP.KUNNR -> KNA1.KUNNR",
             "Customer receiving the delivery"),
)

# The 8 hops of the supplier-delay blast radius, in traversal order.
BLAST_RADIUS_HOPS = (
    "supplier",
    "purchase_orders",
    "schedule_lines",
    "materials",
    "plants",
    "production_orders",
    "sales_orders",
    "deliveries",
    "customers",
)
