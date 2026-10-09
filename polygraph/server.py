"""HTTP API and static web app.

Public deployments protect the Token Factory budget in three layers:
1. Recorded runs replay for free and need no key.
2. Live runs need POLYGRAPH_ACCESS_CODE when it is set, and are rate limited per client and globally.
3. The budget ledger refuses any model call that could cross the lifetime, daily, or per-run cap.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import __version__
from .budget import BudgetExceeded, ledger
from .config import ROOT, ROSTER, settings
from .events import EventBus
from .sources import SourceError, from_github, from_scenario, list_scenarios
from .store import load_run, recorded_index, save_run

WEB_DIST = ROOT / "web" / "dist"
ACCESS_CODE = os.getenv("POLYGRAPH_ACCESS_CODE", "").strip()
PER_HOUR = int(os.getenv("POLYGRAPH_RUNS_PER_HOUR", "4"))
PER_DAY = int(os.getenv("POLYGRAPH_RUNS_PER_DAY", "10"))
GLOBAL_PER_DAY = int(os.getenv("POLYGRAPH_GLOBAL_RUNS_PER_DAY", "40"))
MAX_LIVE = int(os.getenv("POLYGRAPH_MAX_CONCURRENT_RUNS", "2"))

app = FastAPI(title="Polygraph", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=2048)


class LiveRun:
    def __init__(self, run_id: str, bus: EventBus) -> None:
        self.id = run_id
        self.bus = bus
        self.task: asyncio.Task | None = None
        self.started = time.time()
        self.result: dict[str, Any] | None = None
        self.error: str | None = None


RUNS: dict[str, LiveRun] = {}
_hits: dict[str, deque[float]] = defaultdict(deque)
_global_hits: deque[float] = deque()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "unknown")


def _rate_limit(ip: str) -> None:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 86400:
        q.popleft()
    while _global_hits and now - _global_hits[0] > 86400:
        _global_hits.popleft()
    if sum(1 for t in q if now - t < 3600) >= PER_HOUR or len(q) >= PER_DAY:
        raise HTTPException(429, "Live run limit reached for your address. Recorded runs are always available.")
    if len(_global_hits) >= GLOBAL_PER_DAY:
        raise HTTPException(429, "Daily live run limit reached for this deployment. Recorded runs are always available.")
    active = sum(1 for r in RUNS.values() if r.task and not r.task.done())
    if active >= MAX_LIVE:
        raise HTTPException(429, "Polygraph is busy with other live runs. Try again in a minute.")
    q.append(now)
    _global_hits.append(now)


def live_enabled() -> bool:
    return settings.has_llm and ledger.remaining() >= 0.05


# ---------------------------------------------------------------- API


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "llm": settings.has_llm,
        "tavily": settings.has_tavily,
        "executor": settings.executor,
        "live": live_enabled(),
        "access_code_required": bool(ACCESS_CODE),
        "remote_prs": settings.allow_remote_repos,
        "budget": ledger.snapshot(),
        "roster": {k: {"id": v.id, "label": v.label, "role": v.role} for k, v in ROSTER.items()},
    }


@app.get("/api/scenarios")
async def scenarios() -> list[dict[str, Any]]:
    recorded = {r.get("scenario"): r for r in recorded_index() if r.get("scenario")}
    out = []
    for s in list_scenarios():
        rec = recorded.get(s["id"])
        out.append({**s, "recorded": rec})
    return out


@app.get("/api/recorded")
async def recorded() -> list[dict[str, Any]]:
    return recorded_index()


class RunRequest(BaseModel):
    kind: str  # scenario | github
    scenario: str | None = None
    url: str | None = None
    access_code: str | None = None


@app.post("/api/runs")
async def start_run(req: RunRequest, request: Request) -> dict[str, Any]:
    if ACCESS_CODE and not hmac.compare_digest((req.access_code or "").strip(), ACCESS_CODE):
        raise HTTPException(403, "Live runs on this deployment need an access code. Recorded runs are open to everyone.")
    if not settings.has_llm:
        raise HTTPException(503, "This deployment has no Token Factory key configured.")
    try:
        ledger.check_can_start()
    except BudgetExceeded as e:
        raise HTTPException(402, str(e)) from e
    if req.kind == "github" and not settings.allow_remote_repos:
        raise HTTPException(403, "Analysing arbitrary repositories is disabled on this deployment.")
    _rate_limit(_client_ip(request))

    run_id = uuid.uuid4().hex[:12]
    try:
        if req.kind == "scenario" and req.scenario:
            subject = from_scenario(req.scenario, run_id)
        elif req.kind == "github" and req.url:
            subject = await from_github(req.url, run_id)
        else:
            raise HTTPException(400, "Provide a scenario name or a GitHub pull request URL.")
    except SourceError as e:
        raise HTTPException(400, str(e)) from e
    from .engine import Engine

    bus = EventBus()
    live = LiveRun(run_id, bus)
    RUNS[run_id] = live

    async def go() -> None:
        try:
            engine = Engine(subject, bus)
            live.result = await engine.run()
            save_run(live.result, bus.history)
        except Exception as e:  # noqa: BLE001
            live.error = str(e)
            if not bus.closed:
                await bus.emit("error", message=str(e), kind=type(e).__name__)
                bus.close()

    live.task = asyncio.create_task(go())
    return {"id": run_id}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    live = RUNS.get(run_id)
    if live and live.result:
        return JSONResponse(live.result)
    doc = load_run(run_id)
    if doc:
        return JSONResponse(doc["result"])
    if live:
        return JSONResponse({"id": run_id, "status": "running" if not live.error else "error", "error": live.error}, 202)
    raise HTTPException(404, "run not found")


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, speed: float = 1.0) -> EventSourceResponse:
    live = RUNS.get(run_id)
    if live and not live.result:
        q = live.bus.subscribe()

        async def stream():
            while True:
                if await request.is_disconnected():
                    return
                ev = await q.get()
                if ev is None:
                    return
                yield {"event": ev.type, "data": json.dumps(ev.to_dict())}

        return EventSourceResponse(stream(), ping=15)

    doc = load_run(run_id) or ({"result": live.result, "events": [e.to_dict() for e in live.bus.history if e.type != "done"]} if live and live.result else None)
    if not doc:
        raise HTTPException(404, "run not found")
    speed = max(0.5, min(speed, 50.0))

    async def replay():
        prev = None
        for ev in doc["events"]:
            if await request.is_disconnected():
                return
            if prev is not None:
                gap = max(0.0, ev["ts"] - prev)
                await asyncio.sleep(min(gap, 1.5) / speed)
            prev = ev["ts"]
            yield {"event": ev["type"], "data": json.dumps(ev)}
        yield {"event": "done", "data": json.dumps({"type": "done", "ts": time.time(), "data": {"result": doc["result"]}})}

    return EventSourceResponse(replay(), ping=15)


@app.get("/api/runs/{run_id}/comment.md")
async def run_markdown(run_id: str) -> PlainTextResponse:
    doc = load_run(run_id)
    if not doc:
        raise HTTPException(404, "run not found")
    return PlainTextResponse(doc["result"]["artifacts"]["markdown"], media_type="text/markdown")


@app.get("/api/runs/{run_id}/test_polygraph_pinned.py")
async def run_tests(run_id: str) -> PlainTextResponse:
    doc = load_run(run_id)
    if not doc:
        raise HTTPException(404, "run not found")
    return PlainTextResponse(
        doc["result"]["artifacts"]["pinned_tests"],
        media_type="text/x-python",
        headers={"Content-Disposition": 'attachment; filename="test_polygraph_pinned.py"'},
    )


# ---------------------------------------------------------------- static web app


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if WEB_DIST.exists():
        target = (WEB_DIST / path).resolve()
        if path and target.is_file() and WEB_DIST.resolve() in target.parents:
            return FileResponse(target)
        index = WEB_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
    return PlainTextResponse("Polygraph API is running. Build the web app with `npm run build` in web/.", 200)
