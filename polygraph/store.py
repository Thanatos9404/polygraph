"""Persistence for finished runs, including the full event stream so the UI can replay a run exactly."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import ROOT, settings
from .events import Event

RECORDED_DIR = ROOT / "recorded"
_ID = re.compile(r"^[\w-]{4,64}$")


def runs_dir() -> Path:
    p = settings.workdir / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_run(result: dict[str, Any], events: list[Event]) -> Path:
    path = runs_dir() / f"{result['id']}.json"
    doc = {"result": result, "events": [e.to_dict() for e in events if e.type != "done"]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def load_run(run_id: str) -> dict[str, Any] | None:
    if not _ID.match(run_id):
        return None
    for folder in (runs_dir(), RECORDED_DIR):
        p = folder / f"{run_id}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def recorded_index() -> list[dict[str, Any]]:
    out = []
    if not RECORDED_DIR.exists():
        return out
    for p in sorted(RECORDED_DIR.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        r = doc["result"]
        out.append(
            {
                "id": r["id"],
                "title": r["subject"]["title"],
                "url": r["subject"].get("url"),
                "author": r["subject"].get("author"),
                "undeclared": [
                    {"title": d.get("explanation", {}).get("title"), "case": d["examples"][0]["case"], "a": d["examples"][0]["a"], "b": d["examples"][0]["b"]}
                    for d in r.get("divergences", []) if not d.get("declared_by")
                ][:2],
                "baseline_approve": (r.get("baseline") or {}).get("approve"),
                "repo": r["subject"]["repo"],
                "kind": r["subject"]["kind"],
                "scenario": r["subject"].get("scenario"),
                "verdict": r["verdict"].get("label"),
                "headline": r["verdict"].get("headline"),
                "counts": r["verdict"].get("counts"),
                "cost": r["meter"]["total_cost"],
                "duration": r["duration"],
                "created_at": r["created_at"],
            }
        )
    return out
