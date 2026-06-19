# Copilot Instructions

## What This Project Does

Next-Best-Action triage agent for emergency department nurses. Converts incoming patient presentations into a live priority queue that dynamically re-prioritizes as more urgent cases arrive. The same core logic powers both a CLI demo and a Flask web UI.

## Running the Project

```bash
uv sync                          # Install dependencies
uv run python main.py            # CLI demo (uses mock LLM)
uv run python app.py             # Web UI at http://127.0.0.1:5000

# With real OpenAI:
OPENAI_API_KEY=sk-... uv run python main.py
OPENAI_API_KEY=sk-... uv run python app.py
```

No test, lint, or build commands are configured.

## Architecture

Data flows through three layers:

```
Generator → LangGraph Triage → Priority Queue Manager
```

1. **`generator.py`** produces `IncomingItem` instances (mock or LLM-generated clinical cases)
2. **`graph.py`** runs each item through a LangGraph pipeline: `interpret` → `route` → terminal node (`to_queue` / `to_review` / `to_deadletter`)
3. **`queue_manager.py`** holds a `heapq`-backed priority queue plus two safeguard sinks: `review` list and `dead_letter` list
4. **`service.py`** (`ingest()` function + `TriageService` class) ties all three together; `TriageService` is the shared state object for the web UI
5. **`app.py`** is a thin Flask controller over `TriageService`; **`main.py`** is a CLI narrative demo — both share identical business logic through `ingest()`

## Key Conventions

### Schema is the single source of truth
`schema.py` defines acuity levels (1=Emergency → 4=Non-urgent, 99=UNCLASSIFIED sentinel). Changing the use case (e.g., IT on-call queue) means swapping this one file.

### LLM provider via factory
`llm.get_llm()` returns a real `ChatOpenAI(model="gpt-4o-mini", temperature=0)` when `OPENAI_API_KEY` is set, or a keyword-rule `MockLLM` otherwise. Both expose the same interface. Never instantiate the LLM directly outside `llm.py`.

### Graph nodes are side-effect-free
`graph.py` nodes only read/write the `TriageState` TypedDict. Actual queue mutations happen in `service.ingest()` after the graph completes, by inspecting `state["destination"]`.

### Safeguard sinks
- **Review list**: items with `confidence < 0.5` or `level == 99` (UNCLASSIFIED)
- **Dead-letter list**: malformed input (Pydantic validation failure) or LLM triage failure after one retry
- Both sinks are non-fatal; the queue keeps running

### Heap sort key
`QueueEntry.sort_key` is `(level, deadline_timestamp, seq)` — lower level number = higher priority. `seq` is a global monotonic counter that guarantees FIFO within the same level and prevents unstable reordering.

### Deterministic test probes
`llm.py` defines `FORCE_ERROR_MARKER` and `FORCE_REVIEW_MARKER` string constants. Embedding these in an item's `raw_text` forces specific LLM outcomes regardless of provider (real or mock), enabling safeguard testing without mocking. `generator.py` embeds these in `_PROBE_ITEMS` (P-07, P-08, P-09, BAD-01).

### Thread safety
`TriageService` guards all mutations with `threading.Lock()` for Flask's dev-server threading. All state access in `app.py` goes through `TriageService` methods — never touch `qm`, `app` (the graph), or `llm` directly from route handlers.

### Pydantic v2
All three core models (`IncomingItem`, `TriageResult`, `QueueEntry`) use Pydantic v2. Structured LLM output uses `.with_structured_output(TriageResult)`. Field validators use `@field_validator`.
