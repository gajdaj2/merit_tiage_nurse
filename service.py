"""Shared triage logic, used by both the CLI (main.py) and the web UI (app.py).

Keeps a single in-memory queue plus the compiled LangGraph triage flow, so the
two front-ends behave identically.
"""

from __future__ import annotations

import itertools
import threading
from datetime import datetime
from typing import Optional

from generator import generate_items
from graph import build_triage_app
from llm import get_llm, using_mock
from models import IncomingItem, QueueEntry
from queue_manager import PriorityQueueManager


def ingest(raw, qm: PriorityQueueManager, app) -> None:
    """Validate -> triage via the graph -> place into the right sink."""
    # Safeguard 1: malformed input never reaches the graph; it is dead-lettered.
    try:
        item = raw if isinstance(raw, IncomingItem) else IncomingItem(**raw)
    except Exception as exc:  # noqa: BLE001
        item_id = raw.get("id", "?") if isinstance(raw, dict) else "?"
        qm.send_to_dead_letter(item_id, f"malformed item: {exc}")
        return

    state = app.invoke(
        {"item": item, "triage": None, "error": None, "destination": None}
    )
    dest = state["destination"]

    if dest == "deadletter":
        # Safeguard 2: a failed model call is parked, the run continues.
        qm.send_to_dead_letter(item.id, state["error"] or "unknown error")
    elif dest == "review":
        # Safeguard 3: low-confidence / ambiguous -> human review, not the queue.
        qm.send_to_review(
            QueueEntry(item=item, triage=state["triage"], seq=qm.next_seq(),
                       needs_review=True)
        )
    else:
        qm.add(QueueEntry(item=item, triage=state["triage"], seq=qm.next_seq()))


class TriageService:
    """Stateful wrapper around the queue + triage graph for the web UI."""

    def __init__(self) -> None:
        self.llm = get_llm()
        self.app = build_triage_app(self.llm)
        self.qm = PriorityQueueManager()
        self.mode = "Mock (offline)" if using_mock() else "OpenAI"
        self._ids = itertools.count(1)
        self._lock = threading.Lock()  # Flask dev server can be threaded

    def add_text(self, text: str, immediate: bool = False) -> None:
        """Triage a single free-text item typed in the UI."""
        with self._lock:
            ingest(
                IncomingItem(
                    id=f"W-{next(self._ids):03d}",
                    source="web",
                    raw_text=text,
                    deadline=datetime.now() if immediate else None,
                ),
                self.qm,
                self.app,
            )

    def add_raw(self, raw: dict) -> None:
        """Triage a raw dict (may be malformed -> dead-letter)."""
        with self._lock:
            ingest(raw, self.qm, self.app)

    def generate(self, n: int = 6) -> None:
        """Generate a batch of synthetic items and triage them all."""
        with self._lock:
            for item in generate_items(self.llm, n):
                ingest(item, self.qm, self.app)

    def pop_next(self) -> Optional[QueueEntry]:
        """Mark the top item as handled and remove it."""
        with self._lock:
            return self.qm.pop()

    def reset(self) -> None:
        with self._lock:
            self.qm = PriorityQueueManager()
            self._ids = itertools.count(1)

    # read-only views ------------------------------------------------------- #
    def snapshot(self) -> list[QueueEntry]:
        return self.qm.snapshot()

    def peek(self) -> Optional[QueueEntry]:
        return self.qm.peek()

    @property
    def review(self) -> list[QueueEntry]:
        return self.qm.review

    @property
    def dead_letter(self) -> list[tuple[str, str]]:
        return self.qm.dead_letter
