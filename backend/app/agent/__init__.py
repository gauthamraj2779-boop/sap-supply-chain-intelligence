"""Tool-calling agent over the SAP knowledge graph.

The agent chooses *which* graph questions to ask and in what order. It never
computes a figure: every number it reports comes back from a deterministic
handler in ``tools.py``, and the money figures specifically come from the same
orchestrator that serves ``/api/impact``. A bad tool choice therefore produces
a worse answer, never a wrong number.
"""

from app.agent.loop import AgentResult, AgentUnavailable, run_agent
from app.agent.trace import Trajectory, TrajectoryStep

__all__ = [
    "AgentResult",
    "AgentUnavailable",
    "Trajectory",
    "TrajectoryStep",
    "run_agent",
]
