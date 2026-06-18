"""In-memory live priority queue plus the two safeguard sinks.

A heap gives us O(log n) inserts and an O(1) "what's next?" peek, and -- the
behaviour the brief cares about -- when a more urgent item arrives mid-stream
it surfaces ahead of everything already queued, without re-sorting by hand.
"""

from __future__ import annotations

import heapq
import itertools

from models import IncomingItem, QueueEntry, TriageResult


class PriorityQueueManager:
    def __init__(self) -> None:
        self._heap: list[tuple[tuple, int, QueueEntry]] = []
        self._counter = itertools.count()  # global arrival sequence
        self.review: list[QueueEntry] = []  # low-confidence / ambiguous
        self.dead_letter: list[tuple[str, str]] = []  # (item_id, error)

    # -- arrival sequence shared by all sinks so ordering is consistent ----- #
    def next_seq(self) -> int:
        return next(self._counter)

    # -- queue ops ---------------------------------------------------------- #
    def add(self, entry: QueueEntry) -> None:
        # Second tuple element is the seq, which keeps the heap stable and
        # avoids ever comparing QueueEntry objects.
        heapq.heappush(self._heap, (entry.sort_key, entry.seq, entry))

    def peek(self) -> QueueEntry | None:
        """What should I deal with next? (does not remove it)"""
        return self._heap[0][2] if self._heap else None

    def pop(self) -> QueueEntry | None:
        """Take the top item off the queue (it's being worked)."""
        return heapq.heappop(self._heap)[2] if self._heap else None

    def snapshot(self) -> list[QueueEntry]:
        """Current ordering, most urgent first, without mutating the queue."""
        return [e for _, _, e in sorted(self._heap)]

    def __len__(self) -> int:
        return len(self._heap)

    # -- safeguard sinks ---------------------------------------------------- #
    def send_to_review(self, entry: QueueEntry) -> None:
        entry.needs_review = True
        self.review.append(entry)

    def send_to_dead_letter(self, item_id: str, error: str) -> None:
        self.dead_letter.append((item_id, error))
