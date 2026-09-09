# Cached SAP OData `$metadata`

This directory holds EDMX documents downloaded from the SAP Business Accelerator
Hub sandbox, one per service. They are **inputs to the discovery stage only**:
`app/discovery/discover.py` reads the `EntityType` names, key properties and
`NavigationProperty` declarations as independent corroboration for relationships
the profiler found in the data.

Nothing on the request path calls SAP. If this directory is empty, discovery
still runs — it simply loses the `+0.10` OData term in its confidence formula
and says so in `artifacts/discovery.json`.

## Populating the cache

1. Get a sandbox API key: sign in at <https://api.sap.com>, open any of the
   services below, and copy the key from **Show API Key**. It is free with an
   SAP Community account.

2. Put it in `backend/.env` (which is gitignored — never commit it):

   ```
   SAP_API_KEY=<your sandbox key>
   ```

3. Fetch and cache all five documents:

   ```
   cd backend
   venv/bin/python -m app.ingest.sapapi --refresh
   ```

   Without `--refresh` the module only reads what is already here, so a demo can
   never be broken by an expired key or an SAP rate limit.

4. Re-run discovery so the new evidence is used:

   ```
   venv/bin/python -m app.discovery.discover
   ```

## Services

| File | Service | Provides |
|---|---|---|
| `API_BUSINESS_PARTNER.xml` | `API_BUSINESS_PARTNER` | `A_Supplier`, `A_Customer` |
| `API_PRODUCT_SRV.xml` | `API_PRODUCT_SRV` | `A_Product` and its plant/storage views |
| `API_PURCHASEORDER_PROCESS_SRV.xml` | `API_PURCHASEORDER_PROCESS_SRV` | PO header, item, schedule line |
| `API_PRODUCTION_ORDER_2_SRV.xml` | `API_PRODUCTION_ORDER_2_SRV` | Production order and its components |
| `API_OUTBOUND_DELIVERY_SRV.xml` | `API_OUTBOUND_DELIVERY_SRV` | Delivery header and item |

Each is fetched from:

```
https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/<SERVICE>/$metadata
```

with the header `apikey: <SAP_API_KEY>`.

Filenames must match the service name exactly — that is how the loader finds
them. Once downloaded, commit the XML: it is public SAP interface metadata, it
changes rarely, and committing it is what keeps the pipeline reproducible
offline.
