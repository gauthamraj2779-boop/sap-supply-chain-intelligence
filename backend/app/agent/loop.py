"""The agent loop.

Ask the model the question with the tool list attached, run whatever it asks
for, feed the real results back, repeat. Stop when it answers, or when the step
budget runs out -- at which point it is told to answer with what it has rather
than being cut off mid-investigation.

What the loop deliberately does not do: interpret results, compute anything, or
invent a step. Money comes back from ``supplier_delay_impact``, which is the
same orchestrator call ``/api/impact`` makes, and the final prose is run through
the same figure cross-check as the narrator's.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter

from app.agent import tools as agent_tools
from app.agent.trace import Trajectory, TrajectoryStep
from app.engines.llm import get_llm
from app.graph.adapter import GraphBackend
from app.models import ImpactReport
from app.validation.cross_check import CrossCheckResult, verify_narrative

logger = logging.getLogger(__name__)

# Eight steps is the blast radius' own depth: enough to walk supplier to
# customer and check a branch, short enough that a confused run ends visibly
# rather than grinding.
MAX_STEPS = 8

SYSTEM_PROMPT = """You are a supply chain analyst working over an SAP-derived \
knowledge graph. You answer by calling tools, then explaining what they returned.

How to work:
- Start from what the question names. If it names a place, a company or a part \
rather than a supplier number, resolve it with find_suppliers or the ontology first.
- supplier_delay_impact is the only source of financial figures. If the question \
is about exposure, cost, revenue at risk or customers affected, call it.
- Quote every figure exactly as a tool returned it. Never add, scale, convert, \
re-round or estimate a number. If you need a figure no tool returned, say so \
instead of producing one.
- Prefer few, well-chosen calls. You have a budget of {max_steps} tool calls for \
the whole question.
- Every call takes a `reason` argument: one sentence saying why you are making \
that call. Write it before you make the call.

How to answer:
- Plain text, 2 to 5 short paragraphs. Write no markdown syntax at all: no \
asterisks, no bold, no headings, no bullet characters.
- Write USD immediately after every monetary figure, e.g. "95,552,000 USD". \
Never attach USD to a quantity, a day count, a plant code or an order number.
- Name the SAP tables the evidence came from where it helps.
- If the tools could not answer the question, say plainly what is missing and \
what you would need in order to answer. Do not guess and do not fill the gap \
with plausible-sounding detail."""

_FORCE_ANSWER = (
    "Your tool budget is spent. Answer the question now using only the results "
    "already returned above. If they are not sufficient, say exactly what is "
    "missing rather than estimating."
)


class AgentUnavailable(RuntimeError):
    """No model is configured or reachable, so there is no agent to run."""


@dataclass
class AgentResult:
    trajectory: Trajectory
    answer: str
    report: ImpactReport | None = None
    cross_check: CrossCheckResult | None = None


def run_agent(
    backend: GraphBackend,
    question: str,
    shacl_report=None,
    max_steps: int = MAX_STEPS,
    llm=None,
) -> AgentResult:
    """Run one question to an answer, recording every real step on the way."""
    llm = llm or get_llm()
    if not llm.available:
        raise AgentUnavailable(
            f"No LLM is configured, so there is no agent to run: {llm.status().reason}. "
            "Deterministic analysis remains available at POST /api/impact."
        )
    if not llm.supports_tools:
        raise AgentUnavailable(
            f"Provider '{llm.status().provider}' does not expose tool calling through "
            "this client, so the agent cannot run. Deterministic analysis remains "
            "available at POST /api/impact."
        )

    specs = agent_tools.tool_specs(backend)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(max_steps=max_steps)},
        {"role": "user", "content": question},
    ]

    steps: list[TrajectoryStep] = []
    reports: list[ImpactReport] = []
    answer = ""
    stopped = "answered"
    started = perf_counter()

    while len(steps) < max_steps:
        turn = llm.complete_with_tools(messages, specs)
        if turn is None:
            if not steps:
                # Nothing ran; there is no trajectory worth returning.
                raise AgentUnavailable(
                    "The configured model could not be reached. Deterministic "
                    "analysis remains available at POST /api/impact."
                )
            stopped = "model_unreachable"
            break

        if not turn.tool_calls:
            answer = turn.content or ""
            stopped = "answered" if answer else "no_tool_progress"
            break

        messages.append(turn.assistant_message)

        for call in turn.tool_calls:
            if len(steps) >= max_steps:
                # Every tool_call id still needs a reply or the next turn is
                # malformed, so refuse the overflow explicitly.
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": json.dumps({"error": "Step budget exhausted; "
                                                    "no further tool calls will run."}),
                })
                continue

            args = dict(call.arguments)
            # The reason is the model's rationale, not a handler argument.
            thought = str(args.pop("reason", "") or turn.content or "").strip()

            t0 = perf_counter()
            result = agent_tools.execute(
                call.name, call.arguments, backend, shacl_report=shacl_report
            )
            elapsed = int((perf_counter() - t0) * 1000)

            if result.report is not None:
                reports.append(result.report)

            steps.append(TrajectoryStep(
                step=len(steps) + 1,
                thought=thought,
                tool=call.name,
                args=args,
                result_summary=result.error or result.summary,
                sap_tables_touched=result.sap_tables,
                duration_ms=elapsed,
                ok=result.ok,
                error=result.error,
                result=result.data,
            ))

            payload = (
                {"error": result.error}
                if result.error
                else {"summary": result.summary,
                      "sap_tables_read": result.sap_tables,
                      "data": result.data}
            )
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": call.name,
                "content": json.dumps(payload, default=str),
            })
    else:
        stopped = "step_cap"

    # Out of budget, or the model went quiet without answering: ask for the
    # answer one last time, with the tools withdrawn so it has to conclude.
    if not answer and steps:
        messages.append({"role": "user", "content": _FORCE_ANSWER})
        final = llm.complete_with_tools(messages, tools=None)
        if final is not None and final.content:
            answer = final.content
        else:
            # Never invent an analysis. State what happened and let the
            # trajectory below carry the actual findings.
            answer = (
                f"The model stopped responding before it could summarise. "
                f"{len(steps)} tool call(s) completed and their results are in the "
                f"trajectory below; no answer was written over them."
            )
            stopped = "model_unreachable"

    trajectory = Trajectory(
        question=question,
        steps=steps,
        total_duration_ms=int((perf_counter() - started) * 1000),
        final_answer=answer,
        stopped_because=stopped,
        provider=llm.status().provider,
        model=llm.status().model,
    )

    # When several suppliers were analysed, the panels render the largest
    # exposure: that is the one the answer is about.
    report = max(
        reports, key=lambda r: r.financial_exposure.total_financial_exposure
    ) if reports else None

    cross = None
    if report is not None:
        # The same gate the narrator passes through. A figure the agent stated
        # that no engine computed is reported, and the computed values win.
        cross = verify_narrative(
            answer, report.financial_exposure, report.traversal, report.avoidance
        )
        if cross.discrepancies:
            logger.warning(
                "Agent answer contained %d figure(s) with no computed match",
                len(cross.discrepancies),
            )

    return AgentResult(
        trajectory=trajectory, answer=answer, report=report, cross_check=cross
    )
