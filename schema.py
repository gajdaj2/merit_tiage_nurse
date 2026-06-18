"""Priority schema for one use case: an emergency department (ED) triage nurse.

Level 1 is the most urgent. The schema is data, not code: the generator,
the triage prompt, and the queue all read from this single source of truth,
so swapping in another schema (engineer's inbox, IT on-call) is a one-file change.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sentinel level used when triage cannot confidently place an item.
# Higher than any real level number so it never sorts ahead of real work.
UNCLASSIFIED = 99


@dataclass(frozen=True)
class PriorityLevel:
    priority_name: str
    level: int
    description: str


SCHEMA: list[PriorityLevel] = [
    PriorityLevel(
        "Emergency",
        1,
        "Immediate, life-threatening: cardiac arrest, not breathing, severe "
        "bleeding, unresponsive, anaphylaxis, stroke. Resuscitate / see now.",
    ),
    PriorityLevel(
        "Urgent",
        2,
        "Needs prompt care but not immediately life-threatening: suspected "
        "fracture, severe pain, high fever, asthma attack, deep wound.",
    ),
    PriorityLevel(
        "Standard",
        3,
        "Stable and can safely wait: sprains, infections, persistent vomiting, "
        "migraine, moderate pain.",
    ),
    PriorityLevel(
        "Non-urgent",
        4,
        "Minor / routine: prescription refill, cold or sore throat, minor cut, "
        "sick note, follow-up question.",
    ),
]

# Convenience lookups.
LEVELS_BY_NUMBER: dict[int, PriorityLevel] = {p.level: p for p in SCHEMA}
VALID_LEVELS: set[int] = set(LEVELS_BY_NUMBER)


def schema_as_prompt() -> str:
    """Render the schema for inclusion in an LLM prompt."""
    lines = [f"{p.level}. {p.priority_name}: {p.description}" for p in SCHEMA]
    return "\n".join(lines)


def name_for(level: int) -> str:
    if level == UNCLASSIFIED:
        return "UNCLASSIFIED"
    return LEVELS_BY_NUMBER[level].priority_name
