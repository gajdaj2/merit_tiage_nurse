# Next-Best-Action Triage Agent

Turns a messy stream of incoming items into a **live priority queue** for one
role — an **emergency department (ED) triage nurse** — so that at any moment you
can ask *"who should I see next?"* and get the right answer, even as more urgent
patients arrive.

## Run it

```bash
uv sync

# CLI demo (prints the whole flow)
uv run python main.py

# Web UI  ->  open http://127.0.0.1:5000
uv run python app.py
```

Put your key in `.env` (`OPENAI_API_KEY=sk-...`, see `.env.example`) to use the
real model (gpt-4o-mini). With no key it falls back to a deterministic mock LLM,
so the whole pipeline runs offline and reproducibly in either front-end. See
[Web UI](#web-ui) below for the browser version.

## Repo hygiene

- `.gitignore` excludes local environments, caches, and editor artifacts.
- `.env` is ignored; keep secrets local and commit only `.env.example`.

## The use case & schema

ED triage acuity, level 1 = most urgent (`schema.py`):

| Lvl | Name | What it is |
|-----|------|-----------|
| 1 | Emergency | Immediate, life-threatening — cardiac arrest, not breathing, severe bleeding, stroke |
| 2 | Urgent | Prompt care but not immediately life-threatening — fracture, severe pain, asthma |
| 3 | Standard | Stable, can safely wait — sprains, infections, migraine |
| 4 | Non-urgent | Minor / routine — prescription refill, cold, sick note |

The schema is plain data read by the generator, the triage prompt, and the
queue — so swapping in another use case (engineer's inbox, IT on-call) is a
one-file change.

## How it works

1. **Generate** (`generator.py`) — the LLM produces realistic free-text items
   given the schema (offline: a fixed representative batch spanning all levels
   plus the awkward edge cases).
2. **Triage** (`graph.py`) — a **LangGraph** flow handles one item:
   `interpret → route → (to_queue | to_review | to_deadletter)`. The model
   independently decides category, required action, level, and a 0–1 confidence.
3. **Queue** (`queue_manager.py`) — an in-memory heap. `peek()` answers
   "what's next?"; `snapshot()` shows the current ordering; a more urgent item
   arriving mid-stream surfaces ahead of everything already queued.

Why LangGraph: modelling triage as a graph makes each decision point an explicit
edge rather than a buried `if`, so the safeguards and routing are visible and
easy to extend.

## Web UI

A small Flask dashboard (`app.py` + `templates/index.html`) over the same triage
engine. Start it and open <http://127.0.0.1:5000>:

```bash
uv run python app.py
```

It boots with a generated batch so the board isn't empty, and shows the LLM mode
(`Mock` / `OpenAI`) plus live counts in the header. The page has three areas:

- **See next** — the top of the queue ("who should I see next?") with its action,
  and a *Seen — remove & show next* button.
- **Live priority queue** — the full ordering, colour-coded by acuity
  (red Emergency → green Non-urgent), with category, action, confidence, and a ⏱
  marker for items carrying an immediate deadline.
- **Review queue** and **Dead-letter** — the two safeguard sinks, shown live.

Controls:

| Action | What it does |
|--------|--------------|
| **New presentation** (text + *Immediate deadline* checkbox) | Triages a free-text case you type and routes it to the queue / review / dead-letter. The checkbox attaches a "now" deadline so you can watch the tie-break move it within its level. |
| **Generate batch** | Adds another synthetic batch of cases. |
| **Reset** | Clears the queue and both sinks. |

Routes (all mutating routes redirect back to `/`):

| Method & path | Purpose |
|---------------|---------|
| `GET /` | Render the dashboard |
| `POST /add` | Triage one typed presentation |
| `POST /generate` | Generate and triage a batch |
| `POST /next` | Remove the top (handled) item |
| `POST /reset` | Clear queue + sinks |

State is a single in-memory `TriageService` (`service.py`) shared by every
request, guarded by a lock since the Flask dev server can be threaded. The CLI
(`main.py`) and the web UI call the **same** `ingest()` / triage graph, so they
behave identically. It uses Flask's development server — fine for a demo, not for
production.

## The decisions that matter

**Tie-breaking.** Ordering key is `(level, deadline, arrival_seq)`:
1. **Level first** — a higher level *always* preempts a lower one. This is the
   "emergency jumps the queue" dynamic; it never waits behind lower work.
2. **Sooner stated deadline** within the same level.
3. **FIFO (arrival order)** otherwise — fair, deterministic, starvation-free
   within a level, and trivial to explain to the person working the queue.

The demo shows this: a cardiac-arrest pre-alert arrives mid-stream carrying an
"ETA 2 min" deadline and sorts *ahead* of the earlier level-1 patients that had
no deadline.

**Safeguards.**
- *Low confidence (<0.5) or fits no category (level 99)* → quarantined to a
  **review queue** rather than trusted in the live queue; when the model is torn
  it keeps the more-urgent reading and records the runner-up. *Demo: P-07
  (ambiguous chest pain), P-08 (doesn't belong in an ED — the model itself
  returns level 99).*
- *Failure paths* → a **malformed item** (fails Pydantic validation) and a
  **failed model call** (retried once) are both parked in a **dead-letter** list;
  the run never crashes. *Demo: BAD-01 and P-09.*

The `P-*` items are deterministic **probes** carrying hidden markers
(`generator.py` / `llm.py`), so each safeguard fires the same way against the
mock *or* a real model. This matters because a real model (gpt-4o-mini) is
stubbornly confident even on genuinely ambiguous items, so relying on it to
self-report low confidence wouldn't reliably exercise the review path. The
probes are the triage equivalent of fault injection; real classification still
runs on every other item.

## With more time

- Replace the deadline/FIFO tie-break with a real **SLA/age-based urgency score**
  so items escalate as they sit (anti-starvation across levels, not just within).
- **Persist** the queue and dead-letter (SQLite) and add dedup of repeat items.
- An **eval harness**: a labelled item set to measure triage accuracy and tune
  the confidence threshold.
- Human-in-the-loop: let a reviewer resolve review-queue items back into the
  live queue.
