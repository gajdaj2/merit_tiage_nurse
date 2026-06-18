"""Typed data models shared across the pipeline.

Pydantic gives us two things at once:
  1. a schema the LLM fills in via `with_structured_output`, and
  2. a validation boundary -- a malformed item raises here and is caught by
     the orchestrator, which is exactly our failure-path safeguard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from schema import UNCLASSIFIED, VALID_LEVELS


class IncomingItem(BaseModel):
    """A raw item arriving in the inbox, before any interpretation."""

    id: str
    raw_text: str = Field(min_length=1)
    source: str = "inbox"
    # Optional hard deadline the sender stated; used only to break ties
    # *within* a priority level (sooner first).
    deadline: Optional[datetime] = None

    @field_validator("raw_text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_text is blank")
        return v


class TriageResult(BaseModel):
    """The LLM's independent interpretation of one item."""

    category: str = Field(
        description="Short clinical label for the presentation "
        "(e.g. 'chest pain', 'ankle sprain', 'prescription refill')."
    )
    required_action: str = Field(
        description="The single next action the triage nurse should take."
    )
    level: int = Field(
        description="Priority level 1-6 from the schema, or 99 if it fits no "
        "category / cannot be classified."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="0-1 confidence in the chosen level."
    )
    second_choice_level: Optional[int] = Field(
        default=None,
        description="If genuinely torn between two levels, the runner-up.",
    )
    reasoning: str = Field(description="One sentence justifying the level.")

    @field_validator("level", "second_choice_level")
    @classmethod
    def _known_level(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v not in VALID_LEVELS and v != UNCLASSIFIED:
            raise ValueError(f"unknown level {v}")
        return v


class QueueEntry(BaseModel):
    """An interpreted item sitting in the live queue."""

    item: IncomingItem
    triage: TriageResult
    seq: int  # arrival order; stable FIFO tie-breaker
    needs_review: bool = False

    @property
    def sort_key(self) -> tuple:
        """Ordering: level first (1 = most urgent), then sooner deadline,
        then arrival order. See README for the justification."""
        deadline_rank = (
            self.item.deadline.timestamp()
            if self.item.deadline is not None
            else float("inf")
        )
        return (self.triage.level, deadline_rank, self.seq)
