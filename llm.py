"""Single switch point for the model.

If OPENAI_API_KEY is set we use a real ChatOpenAI; otherwise we fall back to a
deterministic MockLLM so the program always runs offline (and so the
failure-path demo is reproducible). Both expose the same surface the rest of
the code relies on: `.with_structured_output(SomePydanticModel).invoke(text)`.
"""

from __future__ import annotations

import os
import re
from typing import Type

from dotenv import load_dotenv
from pydantic import BaseModel

from models import TriageResult

# Load .env at import so OPENAI_API_KEY is available no matter which entry point
# imports this module. Existing real env vars take precedence (override=False).
load_dotenv()

# A marker the demo embeds in one item to force an LLM failure on purpose,
# exercising the retry-then-dead-letter path. Real models never see it matter.
FORCE_ERROR_MARKER = "[[FORCE_LLM_ERROR]]"
# Marker that deterministically yields a low-confidence triage, so the review
# (uncertainty) safeguard is demonstrable against any provider -- a real model
# is often stubbornly confident even on genuinely ambiguous items.
FORCE_REVIEW_MARKER = "[[FORCE_LOW_CONFIDENCE]]"

CONFIDENCE_THRESHOLD = 0.5  # below this -> quarantine to review queue


# --------------------------------------------------------------------------- #
# Mock implementation
# --------------------------------------------------------------------------- #

# Keyword rules per level (1 = most urgent). A match at more than one level is
# treated as ambiguous (-> review). Word-start matching avoids false hits.
_RULES: list[tuple[int, str, list[str]]] = [
    (1, "emergency", [
        "cardiac arrest", "not breathing", "unresponsive", "unconscious",
        "anaphyla", "severe bleeding", "stroke", "seizure", "choking",
        "collapsed", "no pulse",
    ]),
    (2, "urgent", [
        "fracture", "broken", "high fever", "asthma", "deep cut", "deep wound",
        "severe pain", "dehydrat", "head injury",
    ]),
    (3, "standard", [
        "sprain", "infection", "rash", "vomiting", "migraine", "earache",
        "moderate pain", "stitches",
    ]),
    (4, "non-urgent", [
        "prescription", "refill", "sore throat", "common cold", "sick note",
        "follow-up", "minor cut", "advice",
    ]),
]


def _kw_present(keyword: str, text: str) -> bool:
    """Match a keyword/stem only at a word start, so 'cold' does not fire on
    'scold' while the stem 'dehydrat' still catches 'dehydrated'."""
    return re.search(r"(?<![a-z])" + re.escape(keyword), text) is not None


def _mock_triage(text: str) -> TriageResult:
    """Rule-based stand-in for an LLM triage call."""
    low = text.lower()
    hits: list[int] = []
    for level, _label, keywords in _RULES:
        if any(_kw_present(k, low) for k in keywords):
            hits.append(level)

    if not hits:
        return TriageResult(
            category="unclassified",
            required_action="Manually review: no category matched.",
            level=99,
            confidence=0.2,
            reasoning="No schema keywords matched the text.",
        )

    primary = min(hits)  # most urgent matching level
    label = next(lbl for lvl, lbl, _ in _RULES if lvl == primary)

    # Ambiguity: matched more than one level. Default to the more urgent one
    # but record the runner-up and drop confidence so it routes to review.
    if len(hits) > 1:
        runner_up = sorted(hits)[1]
        return TriageResult(
            category=label,
            required_action="Confirm interpretation, then act on the urgent reading.",
            level=primary,
            confidence=0.45,
            second_choice_level=runner_up,
            reasoning=f"Text matches both level {primary} and level {runner_up}; "
            "defaulting to the more urgent pending review.",
        )

    return TriageResult(
        category=label,
        required_action=f"Handle as {label}.",
        level=primary,
        confidence=0.9,
        reasoning=f"Text clearly matches level {primary} ({label}).",
    )


class _MockStructured:
    """Mimics the Runnable returned by `with_structured_output`."""

    def __init__(self, output_model: Type[BaseModel]):
        self._model = output_model

    def invoke(self, prompt: str):
        if self._model is TriageResult:
            # Pull the item text out of the prompt (everything after the marker
            # the triage prompt uses). Falls back to the whole prompt.
            m = re.search(r"ITEM:\s*(.*)", prompt, re.DOTALL)
            return _mock_triage(m.group(1) if m else prompt)
        raise NotImplementedError(
            f"MockLLM has no structured output for {self._model.__name__}"
        )


class MockLLM:
    def with_structured_output(self, output_model: Type[BaseModel]):
        return _MockStructured(output_model)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def get_llm():
    """Return a real ChatOpenAI if a key is present, else the MockLLM."""
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return MockLLM()


def using_mock() -> bool:
    return not os.getenv("OPENAI_API_KEY")


# --------------------------------------------------------------------------- #
# Provider-independent probes (so both safeguards demo against any model)
# --------------------------------------------------------------------------- #

class _FaultInjector:
    """Wraps a triage runnable so the demo's probes behave the same against the
    mock or a real model: FORCE_ERROR_MARKER raises (-> dead-letter), and
    FORCE_REVIEW_MARKER returns a deterministic low-confidence result
    (-> review queue)."""

    def __init__(self, inner):
        self._inner = inner

    def invoke(self, prompt: str):
        if FORCE_ERROR_MARKER in prompt:
            raise RuntimeError("Simulated model/provider failure (fault-injection probe)")
        if FORCE_REVIEW_MARKER in prompt:
            return TriageResult(
                category="possible cardiac event",
                required_action="Get an immediate ECG and senior clinician review.",
                level=1,
                confidence=0.4,
                second_choice_level=2,
                reasoning="Chest pain could be a cardiac emergency or urgent but "
                "non-life-threatening; low confidence, flagged for review (uncertainty probe).",
            )
        return self._inner.invoke(prompt)


def structured_triage(llm):
    """Structured-output runnable for triage, with the demo probes on top."""
    return _FaultInjector(llm.with_structured_output(TriageResult))
