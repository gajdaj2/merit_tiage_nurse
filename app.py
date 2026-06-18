"""Flask web UI for the triage agent.

    uv run python app.py        # then open http://127.0.0.1:5000

Thin layer over service.TriageService: every route mutates or reads the shared
in-memory queue and re-renders the dashboard.
"""

from __future__ import annotations

from flask import Flask, redirect, render_template, request, url_for

from schema import SCHEMA, name_for
from service import TriageService

app = Flask(__name__)
svc = TriageService()

# Bootstrap with a representative batch so the dashboard isn't empty on first load.
svc.generate()

# Bootstrap colour per level (1 = most urgent). Falls back to grey for 99.
_LEVEL_CLASS = {1: "lvl1", 2: "lvl2", 3: "lvl3", 4: "lvl4"}


def _ctx():
    return {
        "mode": svc.mode,
        "schema": SCHEMA,
        "queue": svc.snapshot(),
        "next_item": svc.peek(),
        "review": svc.review,
        "dead_letter": svc.dead_letter,
        "name_for": name_for,
        "level_class": _LEVEL_CLASS,
    }


@app.get("/")
def index():
    return render_template("index.html", **_ctx())


@app.post("/add")
def add():
    text = (request.form.get("text") or "").strip()
    immediate = request.form.get("immediate") == "on"
    if text:
        svc.add_text(text, immediate=immediate)
    return redirect(url_for("index"))


@app.post("/generate")
def generate():
    svc.generate()
    return redirect(url_for("index"))


@app.post("/next")
def next_item():
    svc.pop_next()
    return redirect(url_for("index"))


@app.post("/reset")
def reset():
    svc.reset()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
