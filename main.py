"""Runnable demo of the next-best-action triage agent.

    uv run python main.py            # offline, deterministic mock LLM
    OPENAI_API_KEY=... uv run python main.py   # real model

It generates a messy stream of inbox items, triages each through the LangGraph
flow into a live priority queue, asks "what's next?", then injects a fresh
safety-critical item mid-stream to show it jump the queue. Finally it shows the
two safeguard sinks: the review queue and the dead-letter list.
"""

from __future__ import annotations

from datetime import datetime

from dotenv import load_dotenv

from generator import generate_items
from graph import build_triage_app
from llm import get_llm, using_mock
from models import IncomingItem
from queue_manager import PriorityQueueManager
from schema import name_for
from service import ingest


def show_queue(qm: PriorityQueueManager) -> None:
    if not len(qm):
        print("  (queue empty)")
        return
    for i, e in enumerate(qm.snapshot(), start=1):
        flag = "  <-- NEXT" if i == 1 else ""
        print(
            f"  {i}. [L{e.triage.level} {name_for(e.triage.level):<22}] "
            f"{e.item.id}: {e.triage.required_action}{flag}"
        )


def hr(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    load_dotenv()
    llm = get_llm()
    app = build_triage_app(llm)

    mode = "MOCK (offline, deterministic)" if using_mock() else "OpenAI"
    print(f"Next-Best-Action Triage Agent  |  LLM: {mode}")

    qm = PriorityQueueManager()

    # 1. Generate a messy incoming stream and triage it.
    hr("Triaging the incoming stream")
    items = generate_items(llm)
    for it in items:
        ingest(it, qm, app)
    # A structurally malformed item arrives too (missing raw_text) -> dead-letter.
    ingest({"id": "BAD-01", "source": "api"}, qm, app)

    # 2. The current live queue and "what's next?".
    hr("Live priority queue  (what should I deal with next?)")
    show_queue(qm)
    nxt = qm.peek()
    if nxt:
        print(f"\n>>> NEXT ACTION: {nxt.item.id} -- {nxt.triage.required_action}")

    # 3. A more urgent item arrives mid-stream; it must jump to the front.
    hr("Mid-stream: an emergency arrives")
    urgent = IncomingItem(
        id="LIVE-01",
        source="ambulance",
        raw_text="Ambulance pre-alert: cardiac arrest, CPR in progress, "
        "ETA 2 minutes. Prep resus bay.",
        # Carries an explicit "now" deadline, so within level 1 it sorts ahead
        # of the earlier emergency that had no deadline (the tie-break rule).
        deadline=datetime.now(),
    )
    print(f"  incoming -> {urgent.id}: {urgent.raw_text[:60]}...")
    ingest(urgent, qm, app)
    show_queue(qm)
    print(f"\n>>> NEXT ACTION is now: {qm.peek().item.id}")

    # 4. Drain the queue in priority order (simulating working through it).
    hr("Working the queue top-to-bottom")
    while len(qm):
        e = qm.pop()
        print(f"  done: [L{e.triage.level}] {e.item.id} -- {e.triage.category}")

    # 5. Safeguard sinks.
    hr("Safeguard: review queue (ambiguous / low-confidence)")
    if qm.review:
        for e in qm.review:
            sc = e.triage.second_choice_level
            alt = f", runner-up L{sc}" if sc else ""
            print(
                f"  {e.item.id}: L{e.triage.level} @ conf {e.triage.confidence:.2f}"
                f"{alt} -- {e.triage.reasoning}"
            )
    else:
        print("  (none)")

    hr("Safeguard: dead-letter (malformed / failed calls)")
    if qm.dead_letter:
        for item_id, err in qm.dead_letter:
            print(f"  {item_id}: {err}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
