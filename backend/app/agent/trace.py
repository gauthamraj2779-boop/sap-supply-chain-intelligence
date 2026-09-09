"""The visible trajectory: what the agent decided, and what came back.

Every field is recorded from an execution that actually happened. ``thought`` is
the model's own stated reason for the call; ``sap_tables_touched`` is what the
handler reports having read, never what the model claims. Nothing in here is
reconstructed after the fact, and there is no path that produces a step without
a corresponding tool invocation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field


class TrajectoryStep(BaseModel):
    step: int = Field(description="1-based position in the run")
    thought: str = Field(
        default="",
        description="The model's stated reason for this call, in its own words",
    )
    tool: str
    args: dict = Field(default_factory=dict, description="Arguments as dispatched")
    result_summary: str = Field(description="One line describing what came back")
    sap_tables_touched: list[str] = Field(
        default_factory=list,
        description="Tables the handler actually read, reported by the handler",
    )
    duration_ms: int = 0
    ok: bool = True
    error: str | None = None
    result: Any = Field(
        default=None,
        description="The tool's raw result, exactly as it was fed back to the model",
    )


class Trajectory(BaseModel):
    question: str
    steps: list[TrajectoryStep] = Field(default_factory=list)
    total_duration_ms: int = 0
    final_answer: str = ""
    stopped_because: str = Field(
        default="answered",
        description="answered | step_cap | model_unreachable | no_tool_progress",
    )
    provider: str | None = None
    model: str | None = None

    @computed_field
    @property
    def step_count(self) -> int:
        return len(self.steps)

    @computed_field
    @property
    def sap_tables_touched(self) -> list[str]:
        """Union of the tables the run actually read, in first-touch order."""
        seen: list[str] = []
        for s in self.steps:
            for t in s.sap_tables_touched:
                if t not in seen:
                    seen.append(t)
        return seen

    @computed_field
    @property
    def tools_used(self) -> list[str]:
        return [s.tool for s in self.steps]
