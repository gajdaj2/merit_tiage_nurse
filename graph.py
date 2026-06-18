"""LangGraph flow that triages ONE item and decides where it belongs.

Flow:           interpret ──► route ──► (to_queue | to_review | to_deadletter) ──► END

Modelling triage as a graph (rather than an inline function) makes the
decision points explicit and easy to extend: each safeguard is its own edge,
not a buried `if`. The graph itself is side-effect free -- it only sets a
`destination`; the caller (main) does the actual placement into the queue.
"""

from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from llm import CONFIDENCE_THRESHOLD, structured_triage
from models import IncomingItem, TriageResult
from schema import UNCLASSIFIED, schema_as_prompt

_PROMPT = """You are an emergency department triage nurse assessing an incoming
patient. Classify the case into exactly one acuity level using this schema
(1 = most urgent):

{schema}

Decide the category, the single required action, the level (1-4, or 99 if it
does not belong in an ED), your confidence (0-1), a runner-up level only if you
are torn, and one sentence of clinical reasoning.

Be honest about uncertainty: if the case could reasonably belong to two levels,
name the runner-up in second_choice_level. If it does not belong here, use 99.

ITEM: {text}"""


class TriageState(TypedDict):
    item: IncomingItem
    triage: Optional[TriageResult]
    error: Optional[str]
    destination: Optional[str]


def build_triage_app(llm):
    """Compile a triage graph bound to a given LLM (real or mock)."""

    structured = structured_triage(llm)

    def interpret(state: TriageState) -> dict:
        """Call the model, with one retry, to interpret the item."""
        prompt = _PROMPT.format(
            schema=schema_as_prompt(), text=state["item"].raw_text
        )
        last_err: Exception | None = None
        for _attempt in range(2):  # initial try + one retry
            try:
                return {"triage": structured.invoke(prompt), "error": None}
            except Exception as exc:  # noqa: BLE001 - we want any failure here
                last_err = exc
        return {"triage": None, "error": f"triage failed: {last_err}"}

    def route(state: TriageState) -> str:
        """Pick the destination edge based on the triage outcome."""
        if state["error"] is not None:
            return "to_deadletter"
        triage = state["triage"]
        assert triage is not None
        # Quarantine to review if nothing fits (99) or the model is unsure.
        if triage.level == UNCLASSIFIED or triage.confidence < CONFIDENCE_THRESHOLD:
            return "to_review"
        return "to_queue"

    # Terminal nodes only stamp the decision; placement happens in main.
    def to_queue(state: TriageState) -> dict:
        return {"destination": "queue"}

    def to_review(state: TriageState) -> dict:
        return {"destination": "review"}

    def to_deadletter(state: TriageState) -> dict:
        return {"destination": "deadletter"}

    g = StateGraph(TriageState)
    g.add_node("interpret", interpret)
    g.add_node("to_queue", to_queue)
    g.add_node("to_review", to_review)
    g.add_node("to_deadletter", to_deadletter)

    g.add_edge(START, "interpret")
    g.add_conditional_edges(
        "interpret",
        route,
        {
            "to_queue": "to_queue",
            "to_review": "to_review",
            "to_deadletter": "to_deadletter",
        },
    )
    for terminal in ("to_queue", "to_review", "to_deadletter"):
        g.add_edge(terminal, END)

    return g.compile()
