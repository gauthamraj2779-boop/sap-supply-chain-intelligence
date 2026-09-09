"""Natural-language -> Cypher translation result.

The generated query is returned whether or not it passed validation and whether
or not the backend could run it. A rejected query with its reason is a more
useful answer than a silent failure, and a validated-but-unexecuted query is
still the honest answer to "what would this question look like against the
graph?" when no Neo4j instance is attached.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CypherTranslation(BaseModel):
    question: str

    query: str | None = Field(
        default=None,
        description="The query the model produced. Present even when validation rejected it.",
    )
    valid: bool = Field(
        default=False, description="Whether the query passed the read-only/schema gate"
    )
    reason: str | None = Field(
        default=None, description="Why validation rejected the query, or why none was produced"
    )
    generated_by: str = "unavailable"

    limit_injected: bool = Field(
        default=False, description="A default LIMIT was appended because the query had none"
    )
    labels_used: list[str] = Field(default_factory=list)
    relationship_types_used: list[str] = Field(default_factory=list)

    executed: bool = False
    row_count: int = 0
    rows: list[dict] = Field(default_factory=list)
    execution_note: str | None = Field(
        default=None, description="What happened when execution was attempted"
    )
