# Problem Statement: AI-Powered SAP Knowledge Graph

SAP contains extensive business knowledge across technical metadata, master data and transactions. However, this knowledge is distributed across complex tables, CDS views, applications and documents. Understanding how suppliers, materials, purchase orders, inventory, plants, production orders and customer deliveries relate to one another requires specialized SAP expertise and significant manual effort.

Traditional SQL depends on predefined joins, vector search cannot reliably traverse business relationships, and LLMs may generate incomplete or unsupported answers when SAP context is missing.

The challenge is to build an AI-powered solution that:
- Discovers entities and relationships from SAP metadata and data.
- Converts technical SAP structures into a business ontology.
- Populates a governed knowledge graph with actual SAP records.
- Enables natural-language, multi-hop reasoning across connected business objects.
- Produces explainable answers with calculations, source lineage and confidence.

The POC should answer:
**If a supplier is delayed, which materials, plants, production orders and customer deliveries will be affected, and why?**

The solution should prove that combining AI, ontology and knowledge-graph technologies can provide enterprise agents with an accurate, explainable and reusable semantic foundation for understanding SAP data.
