"""Command line interface: `polygraph pr <url>`, `polygraph local <repo>`, `polygraph scenario <name>`, `polygraph serve`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown

from .config import settings
from .events import Event, EventBus

app = typer.Typer(add_completion=False, help="Polygraph checks pull request claims by experiment.")
console = Console(highlight=False)

STAGE_NAMES = {
    "ingest": "Ingest",
    "claims": "Claim ledger",
    "research": "Research",
    "plan": "Experiment plan",
    "probes": "Probe synthesis",
    "calibrate": "Calibration",
    "execute": "Twin execution",
    "compare": "Divergence mining",
    "verdict": "Verdict",
}


def _printer(ev: Event) -> None:
    d = ev.data
    t = ev.type
    if t == "stage":
        name = STAGE_NAMES.get(d["key"], d["key"])
        if d["state"] == "start":
            extra = f"  [dim]{d.get('model') or d.get('provider') or d.get('executor') or ''}[/dim]"
            console.print(f"[bold]>[/bold] {name}{extra}")
        else:
            info = {k: v for k, v in d.items() if k in ("count", "clusters", "cases", "label", "flaky", "skipped", "probes")}
            console.print(f"  [dim]done in {d.get('seconds', 0)}s {info if info else ''}[/dim]")
    elif t == "claim":
        tag = " (implied)" if d.get("implicit") else ""
        console.print(f"  {d['id']}  {d['statement']}{tag}")
    elif t == "experiment":
        console.print(f"  {d['id']}  {d['target']}  [dim]{d['mode']} {','.join(d['claims'])}[/dim]")
    elif t == "execution":
        if d.get("error"):
            console.print(f"  {d['id']}  [red]error[/red] {d['error'][:160]}")
        else:
            console.print(
                f"  {d['id']}  {d.get('cases', 0)} inputs  {d.get('diverge', 0)} diverge  {d.get('flaky', 0)} noisy"
            )
    elif t == "divergence":
        title = d.get("explanation", {}).get("title", d["kind"])
        console.print(f"  {d['id']}  {title}  [dim]{d['count']}/{d['total']} {d['target']}[/dim]")
    elif t == "repair":
        console.print(f"  [yellow]repairing {d['id']}[/yellow] [dim]{d['error'][:120]}[/dim]")
    elif t == "universe" and d.get("state") == "ready":
        console.print(f"  [dim]universe {d['label']} ready ({d.get('backend')}, {d.get('python', '')})[/dim]")
    elif t == "research":
        if d.get("kind") == "dependency":
            console.print(f"  [dim]{d['package']} {d['before']} -> {d['after']}: {len(d['sources'])} sources[/dim]")
        else:
            console.print(f"  [dim]{len(d.get('pages', []))} linked pages read[/dim]")
    elif t == "suite" and d.get("state") == "done":
        console.print(f"  [dim]test suite in universe {d['label']}: {d.get('summary') or d.get('error', '')}[/dim]")
    elif t == "log":
        console.print(f"  [dim]{d['text']}[/dim]")
    elif t == "error":
        console.print(f"[red]error:[/red] {d['message']}")


async def _run(subject, executor: Optional[str], out: Optional[Path]) -> dict:
    from .engine import Engine
    from .store import save_run

    bus = EventBus()
    bus.add_sink(_printer)
    engine = Engine(subject, bus, executor=executor)
    result = await engine.run()
    path = save_run(result, bus.history)
    console.print()
    console.print(Markdown(result["artifacts"]["markdown"]))
    console.print(f"\n[dim]saved {path}[/dim]")
    if out:
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


@app.command()
def pr(url: str, executor: Optional[str] = None, out: Optional[Path] = None) -> None:
    """Analyse a public GitHub pull request."""
    from .sources import from_github

    async def go():
        subject = await from_github(url)
        return await _run(subject, executor, out)

    _exit(asyncio.run(go()))


@app.command()
def local(
    repo: Path = typer.Argument(Path(".")),
    base: str = typer.Option("main", help="Base ref"),
    head: str = typer.Option("HEAD", help="Head ref, or WORKTREE for uncommitted changes"),
    title: Optional[str] = None,
    body: Optional[str] = None,
    executor: Optional[str] = None,
    out: Optional[Path] = None,
) -> None:
    """Analyse two refs of a local git repository."""
    from .sources import from_local

    subject = from_local(repo, base, head, title, body)
    _exit(asyncio.run(_run(subject, executor, out)))


@app.command()
def scenario(name: str, executor: Optional[str] = None, out: Optional[Path] = None) -> None:
    """Analyse one of the bundled scenarios."""
    from .sources import from_scenario

    _exit(asyncio.run(_run(from_scenario(name), executor, out)))


@app.command()
def record(
    name: str,
    from_run: Optional[str] = typer.Option(None, help="Promote an existing run instead of running again"),
    pr_url: Optional[str] = typer.Option(None, "--pr", help="Record a public GitHub PR instead of a scenario"),
) -> None:
    """Run a bundled scenario and store it as a recorded case file that the web app replays for free."""
    from .sources import from_scenario
    from .store import RECORDED_DIR, load_run, runs_dir

    if from_run:
        doc = load_run(from_run)
        if not doc:
            raise typer.BadParameter(f"no run {from_run}")
    else:
        if pr_url:
            from .sources import from_github

            async def go():
                return await _run(await from_github(pr_url), None, None)

            asyncio.run(go())
        else:
            asyncio.run(_run(from_scenario(name), None, None))
        latest = max(runs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
        doc = json.loads(latest.read_text(encoding="utf-8"))
    from .baseline import review

    if pr_url:
        from .sources import from_github

        subject = asyncio.run(from_github(pr_url))
    else:
        subject = from_scenario(name)
    doc["result"]["baseline"] = asyncio.run(review(subject))
    case_id = name if pr_url else f"case-{name}"
    doc["result"]["id"] = case_id
    if not pr_url:
        doc["result"]["subject"]["scenario"] = name
        for ev in doc["events"]:
            if ev["type"] == "run":
                ev["data"]["subject"]["scenario"] = name
    RECORDED_DIR.mkdir(exist_ok=True)
    (RECORDED_DIR / f"{case_id}.json").write_text(json.dumps(doc), encoding="utf-8")
    console.print(f"recorded {case_id}: {doc['result']['verdict']['label']}, ${doc['result']['meter']['total_cost']:.4f}")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 7860) -> None:
    """Start the web app and API."""
    import uvicorn

    uvicorn.run("polygraph.server:app", host=host, port=port, log_level="info")


def _exit(result: dict) -> None:
    label = result.get("verdict", {}).get("label")
    raise typer.Exit(code=1 if label == "inconsistent" else 0)


if __name__ == "__main__":
    app()
