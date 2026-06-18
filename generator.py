"""Generate synthetic incoming items.

With a real LLM this asks the model for realistic free-text scenarios given the
schema. Offline (mock), it returns a fixed, representative batch that spans
every level plus the awkward cases the safeguards exist for: one ambiguous
item, one that fits no category, one that will trip a model failure, and one
that is structurally malformed.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from llm import FORCE_ERROR_MARKER, FORCE_REVIEW_MARKER, using_mock
from models import IncomingItem
from schema import schema_as_prompt


class _GenItem(BaseModel):
    raw_text: str = Field(description="Free-text triage note as a nurse would receive it.")


class _GenBatch(BaseModel):
    items: List[_GenItem]


_GEN_PROMPT = """You generate realistic patient presentations for an emergency
department triage nurse. Given this priority schema (1 = most urgent):

{schema}

Produce {n} varied, realistic free-text triage notes spanning different acuity
levels. Include at least one genuinely ambiguous case (could be two levels) and
one that does not belong in an ED at all. Write them as a triage note / walk-in
complaint -- do NOT state the level."""


# Deterministic offline batch, one per level (mock mode only).
_MOCK_CLEAN: list[dict] = [
    {"id": "M-01", "source": "ambulance",
     "raw_text": "Adult male collapsed in the waiting room, unresponsive and not "
                 "breathing. Staff have started CPR."},
    {"id": "M-02", "source": "walk-in",
     "raw_text": "Child fell off a trampoline, suspected fracture of the right "
                 "forearm, visibly deformed and in a lot of pain."},
    {"id": "M-03", "source": "walk-in",
     "raw_text": "Adult rolled their ankle playing football, painful ankle sprain, "
                 "swollen but able to walk, otherwise well."},
    {"id": "M-04", "source": "front-desk",
     "raw_text": "Patient here just for a prescription refill of their regular "
                 "blood pressure tablets, no new symptoms."},
]

# Curated edge-case probes that exercise each safeguard. Appended to the stream
# in BOTH modes so the safeguards are demonstrated even against a real model
# (which otherwise tends to generate only clean, easily-classified items).
_PROBE_ITEMS: list[dict] = [
    # Ambiguous: could be a cardiac emergency OR an urgent-but-stable case.
    # Marker makes the low-confidence routing deterministic across providers.
    {"id": "P-07", "source": "walk-in",
     "raw_text": "Middle-aged man with central chest pain and sweating for the "
                 "last hour, looks anxious but is talking normally. "
                 + FORCE_REVIEW_MARKER},
    # Does not belong in an ED -> quarantined for review.
    {"id": "P-08", "source": "front-desk",
     "raw_text": "Visitor asking which floor the hospital pharmacy is on."},
    # Forces a model failure (provider-independent) -> retry then dead-letter.
    {"id": "P-09", "source": "system",
     "raw_text": f"Routine bloodwork results uploaded to the record. {FORCE_ERROR_MARKER}"},
]


def generate_items(llm, n: int = 6) -> list[IncomingItem]:
    if using_mock():
        base = _MOCK_CLEAN
    else:
        structured = llm.with_structured_output(_GenBatch)
        batch: _GenBatch = structured.invoke(
            _GEN_PROMPT.format(schema=schema_as_prompt(), n=n)
        )
        base = [
            {"id": f"G-{i:02d}", "source": "generated", "raw_text": it.raw_text}
            for i, it in enumerate(batch.items, start=1)
        ]
    return [IncomingItem(**d) for d in base + _PROBE_ITEMS]
