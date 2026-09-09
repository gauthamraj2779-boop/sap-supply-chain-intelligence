"""Schema discovery: derive entities and relationships from SAP metadata + data.

Two stages, deliberately separated so the expensive one is optional:

``profile``   deterministic column statistics and containment ratios. No LLM,
              no network, reproducible byte-for-byte.
``discover``  one structured LLM call that reads that evidence and names the
              business entities. Falls back to a purely deterministic
              derivation when no LLM is configured.
"""
