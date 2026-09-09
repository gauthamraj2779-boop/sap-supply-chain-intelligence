"""A value that was not read from the source record but derived from its peers.

An estimate is only defensible if the reader can see it is one, see what it was
derived from, and see how much evidence stood behind it. All three travel with
the number rather than in a footnote.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EstimatedValue(BaseModel):
    entity: str = Field(description="Record type, e.g. 'PurchaseOrderItem'")
    key: str = Field(description="Record key, e.g. 'EBELN=4500012/EBELP=00010'")
    sap_field: str = Field(description="The field that was absent, e.g. 'EKPO.NETWR'")

    estimated_value: float
    basis: str = Field(description="How the estimate was derived, in full")
    sample_size: int = Field(description="How many source records the basis averaged over")
    is_estimated: bool = True
