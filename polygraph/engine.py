"""The Polygraph pipeline: claims, research, experiment design, probe synthesis, twin execution, verdict."""

from __future__ import annotations

import ast
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from . import prompts
from .analysis import Target, TreeDiff, diff_trees
from .budget import ledger
from .compare import Cluster, ProbeStats, cluster, compare
from .config import ROSTER, settings
from .events import EventBus
from .llm import LLMError, Meter, TokenFactory, extract_code
from .report import build_markdown, build_pinned_tests
from .research import dependency_notes, linked_pages, render_notes
from .sandbox import Executor, SandboxError, Universe, get_executor, has_tests
from .sources import Subject, requirements_for

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class EnvironmentProblem(Exception):
    """The universe cannot import the project at all. No probe rewrite can fix this."""


@dataclass
class Experiment:
    id: str
    target: Target
    mode: str
    claims: list[str]
    focus: str
    hypotheses: list[str]
    round: int = 1
    code: str = ""
    repaired: bool = False
    error: str | None = None
    stats: ProbeStats | None = None
    docs: dict[str, Any] = field(default_factory=dict)

    def import_line(self) -> str:
        top = self.target.name.split(".")[0]
        return f"from {self.target.module} import {top}" if self.target.module else f"import {top}"

    def to_dict(self) -> dict[str, Any]:
        s = self.stats
        return {
            "id": self.id,
            "target": self.target.qualname,
            "status": self.target.status,
            "mode": self.mode,
            "claims": self.claims,
            "focus": self.focus,
            "hypotheses": self.hypotheses,
            "round": self.round,
            "code": self.code,
            "repaired": self.repaired,
            "error": self.error,
            "stats": None
            if s is None
            else {
                "cases": s.cases,
                "agree": s.agree,
                "diverge": s.diverge,
                "flaky": s.flaky,
                "load_error_a": s.load_error_a,
                "load_error_b": s.load_error_b,
                "speed": s.speed(),
            },
        }


def _valid_calls(raw: Any) -> list[str]:
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, str) or len(c) > 400:
            continue
        c = c.strip().rstrip(";")
        try:
            tree = ast.parse(c, mode="eval")
        except SyntaxError:
            continue
        if isinstance(tree.body, ast.Call):
            out.append(c)
    return out


def _witness_probe(e: "Experiment", calls: list[str]) -> str:
    mod = e.target.module
    lines = [
        f"# Witness calls from the experiment plan for {e.target.qualname}, executed verbatim in both universes.",
        f"from {mod} import *  # noqa: F403" if mod else "",
        e.import_line(),
        "import importlib as _importlib",
        "",
        f"_NS = dict(vars(_importlib.import_module({mod!r})))" if mod else "_NS = {}",
        "_NS.update({k: v for k, v in globals().items() if not k.startswith('_')})",
        "",
        "CASES = [",
        *[f"    {c!r}," for c in calls],
        "]",
        "",
        "",
        "def run(case):",
        "    return eval(case, _NS)",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def _syntax_error(code: str) -> str | None:
    try:
        compile(code, "probe", "exec")
    except SyntaxError as err:
        return f"SyntaxError: {err.msg} (line {err.lineno})"
    return None


def _truncate(text: str | None, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more characters]"


class Engine:
    def __init__(self, subject: Subject, bus: EventBus | None = None, executor: str | None = None) -> None:
        ledger.check_can_start()
        self.subject = subject
        self.bus = bus or EventBus()
        self.meter = Meter()
        self.llm = TokenFactory(self.bus, self.meter)
        self.executor: Executor = get_executor(executor or settings.executor)
        self.diff: TreeDiff | None = None
        self.claims: list[dict[str, Any]] = []
        self.intent = ""
        self.research: list[dict[str, Any]] = []
        self.experiments: list[Experiment] = []
        self.clusters: list[Cluster] = []
        self.stats: dict[str, ProbeStats] = {}
        self.ledger: list[dict[str, Any]] = []
        self.verdict: dict[str, Any] = {}
        self.universes: dict[str, Universe] = {}
        self.suites: dict[str, dict[str, Any]] = {}
        self._suite_task: asyncio.Task | None = None
        self._diffs: list = []
        self._follow_ups: list[dict[str, Any]] = []
        self._exec_sem = asyncio.Semaphore(settings.exec_concurrency)
        self._t0 = time.time()
        self._stage_t: dict[str, float] = {}

    # ------------------------------------------------------------------ events

    async def stage(self, key: str, state: str, **data: Any) -> None:
        if state == "start":
            self._stage_t[key] = time.time()
        else:
            data["seconds"] = round(time.time() - self._stage_t.get(key, time.time()), 2)
        await self.bus.emit("stage", key=key, state=state, **data)

    async def log(self, text: str, **data: Any) -> None:
        await self.bus.emit("log", text=text, **data)

    # ------------------------------------------------------------------ pipeline

    async def run(self) -> dict[str, Any]:
        await self.bus.emit("run", state="start", subject=self.subject.public(), executor=self.executor.name,
                            roster={k: {"id": v.id, "label": v.label, "role": v.role} for k, v in ROSTER.items()})
        try:
            await self._ingest()
            universes_task = asyncio.create_task(self._prepare_universes())
            await asyncio.gather(self._claims(), self._research())
            if not self.diff or not self.diff.targets:
                await self.log("No Python functions changed. Nothing to execute; the verdict rests on the claim ledger.")
                universes_task.cancel()
                await self._verdict(final=True)
            else:
                await self._plan()
                await self._synthesize(self.experiments)
                await universes_task
                self._suite_task = asyncio.create_task(self._suites())
                await self._execute(self.experiments)
                await self._suite_task
                await self._analyse()
                await self._verdict(final=settings.max_rounds <= 1)
                rounds = 1
                while rounds < settings.max_rounds and self._follow_ups:
                    rounds += 1
                    added = self._make_follow_ups(rounds)
                    if not added:
                        break
                    await self.log(f"Round {rounds}: {len(added)} follow-up experiments for unverified claims.")
                    await self._synthesize(added)
                    await self._execute(added)
                    await self._analyse()
                    await self._verdict(final=rounds >= settings.max_rounds)
            result = self.result()
            await self.bus.emit("done", result=result)
            return result
        except Exception as e:
            await self.bus.emit("error", message=str(e), kind=type(e).__name__)
            raise
        finally:
            await self.executor.close()
            self.bus.close()

    async def _ingest(self) -> None:
        await self.stage("ingest", "start")
        self.diff = await asyncio.to_thread(
            diff_trees, self.subject.root_a, self.subject.root_b, settings.max_targets
        )
        await self.stage("ingest", "end", **self.diff.summary())

    async def _prepare_universes(self) -> None:
        req_a = requirements_for(self.subject.root_a)
        req_b = requirements_for(self.subject.root_b)
        await self.bus.emit("universe", label="A", state="building", deps=bool(req_a))
        await self.bus.emit("universe", label="B", state="building", deps=bool(req_b))

        async def one(label: str, root, req) -> None:
            u = await self.executor.prepare(label, root, req)
            self.universes[label] = u
            await self.bus.emit("universe", label=label, state="ready", **u.meta)

        await asyncio.gather(one("A", self.subject.root_a, req_a), one("B", self.subject.root_b, req_b))

    async def _suites(self) -> None:
        """Run the project's own test suite in both universes. Green tests next to red behavior is the point."""
        if not has_tests(self.subject.root_b) and not has_tests(self.subject.root_a):
            return
        await self.bus.emit("suite", state="start")

        async def one(label: str) -> None:
            try:
                res = await self.executor.run_suite(self.universes[label], timeout=180)
            except SandboxError as e:
                res = {"ran": False, "error": str(e)[:400]}
            self.suites[label] = res
            await self.bus.emit("suite", state="done", label=label, **res)

        await asyncio.gather(one("A"), one("B"))

    async def _claims(self) -> None:
        await self.stage("claims", "start", model=ROSTER["ultra"].label)
        changed = "\n".join(f"- {t.qualname} ({t.status})" for t in (self.diff.targets if self.diff else []))
        user = (
            f"{self.subject.pr_text()}\n\nRepository: {self.subject.repo}\n"
            f"Changed symbols (context only):\n{changed or '(none)'}\n\n"
            f"Diff excerpt (context only):\n{_truncate(self.diff.unified_diff if self.diff else '', 12000)}"
        )
        data = await self.llm.json("ultra", prompts.CLAIMS_SYSTEM, user, purpose="claim ledger", max_tokens=3000, require="claims")
        self.intent = str(data.get("intent", ""))
        claims = []
        for i, c in enumerate(data.get("claims", [])[:8], start=1):
            claims.append(
                {
                    "id": f"C{i}",
                    "statement": str(c.get("statement", "")).strip(),
                    "quote": str(c.get("quote", "")).replace("**", "").replace("`", "").strip().strip('"“”').strip(),
                    "kind": c.get("kind", "other"),
                    "implicit": bool(c.get("implicit", False)),
                    "testable": bool(c.get("testable", True)),
                    "targets_hint": c.get("targets_hint", []) or [],
                }
            )
        self.claims = claims
        for c in claims:
            await self.bus.emit("claim", **c)
        await self.stage("claims", "end", count=len(claims), intent=self.intent)

    async def _research(self) -> None:
        await self.stage("research", "start", provider="Tavily")
        if not settings.has_tavily:
            await self.stage("research", "end", skipped="TAVILY_API_KEY not set")
            return
        jobs = [dependency_notes(d) for d in (self.diff.dependency_changes if self.diff else [])[:4]]
        jobs.append(linked_pages(self.subject.body))
        results = await asyncio.gather(*jobs, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                await self.log(f"Research lookup failed: {r}")
            elif r:
                self.research.append(r)
                await self.bus.emit("research", **r)
        await self.stage("research", "end", count=len(self.research))

    async def _plan(self) -> None:
        assert self.diff
        await self.stage("plan", "start", model=ROSTER["ultra"].label)
        targets = self.diff.targets
        blocks = []
        for t in targets:
            blocks.append(
                f"## {t.qualname}  [{t.status}: {t.reason}]\n"
                f"Before (A):\n```python\n{_truncate(t.source_a or '(does not exist)', 5000)}\n```\n"
                f"After (B):\n```python\n{_truncate(t.source_b or '(does not exist)', 5000)}\n```"
            )
        user = (
            f"Claims:\n{json.dumps(self.claims, indent=1)}\n\n"
            f"Targets ({len(targets)}):\n" + "\n\n".join(blocks)
        )
        if self.research:
            user += "\n\nResearch notes:\n" + render_notes(self.research)
        system = prompts.PLAN_SYSTEM.replace("{max_targets}", str(settings.max_targets))
        try:
            data = await self.llm.json("ultra", system, user, purpose="experiment plan", max_tokens=5000, require="experiments")
            planned = data.get("experiments", [])
        except LLMError as e:
            await self.log(f"Planner failed ({e}); falling back to one broad experiment per target.")
            planned = []
        by_q = {t.qualname: t for t in targets}
        seen: set[str] = set()
        rejected = []
        planned_count: dict[str, int] = {}
        witness_calls: dict[str, tuple[Experiment, list[str]]] = {}
        for p in planned:
            q = self._match_target(str(p.get("target", "")), targets)
            if q is None:
                rejected.append(str(p.get("target", "")))
                continue
            if planned_count.get(q, 0) >= (2 if len(targets) <= 3 else 1):
                continue
            planned_count[q] = planned_count.get(q, 0) + 1
            seen.add(q)
            t = by_q[q]
            mode = "solo" if t.source_a is None else "twin"
            exp = Experiment(
                id=f"P{len(self.experiments) + 1}",
                target=t,
                mode=mode,
                claims=[c for c in p.get("claims", []) if isinstance(c, str)],
                focus=str(p.get("focus", "")),
                hypotheses=[str(h) for h in p.get("hypotheses", [])][:6],
            )
            self.experiments.append(exp)
            calls = _valid_calls(p.get("calls", []))
            if calls:
                witness_calls.setdefault(t.qualname, (exp, []))[1].extend(calls)
        # Every changed public function gets probed, even if the planner skipped it.
        for t in targets:
            if t.qualname in seen or t.status == "removed" or len(self.experiments) >= settings.max_targets:
                continue
            if t.status in ("changed", "dependency", "added") or not self.experiments:
                self.experiments.append(
                    Experiment(
                        id=f"P{len(self.experiments) + 1}",
                        target=t,
                        mode="solo" if t.source_a is None else "twin",
                        claims=[],
                        focus="Broad sweep of typical, boundary, and malformed inputs.",
                        hypotheses=["Outputs may differ wherever the changed lines are reached."],
                    )
                )
        # The planner's concrete calls run verbatim as their own probe: every hypothesis gets a direct witness.
        for q, (src, calls) in witness_calls.items():
            calls = list(dict.fromkeys(calls))[:14]
            w = Experiment(
                id=f"P{len(self.experiments) + 1}",
                target=src.target,
                mode=src.mode,
                claims=sorted({c for e in self.experiments if e.target.qualname == q for c in e.claims}),
                focus="Witness calls written by the planner for each hypothesis and each example in the PR, executed verbatim.",
                hypotheses=src.hypotheses,
            )
            w.code = _witness_probe(w, calls)
            self.experiments.append(w)
        if rejected:
            await self.log(f"Planner named unknown targets, ignored: {', '.join(rejected[:5])}")
        for e in self.experiments:
            await self.bus.emit("experiment", **e.to_dict())
        await self.stage("plan", "end", count=len(self.experiments))

    @staticmethod
    def _match_target(name: str, targets: list[Target]) -> str | None:
        name = name.strip().strip("`")
        by_q = {t.qualname: t.qualname for t in targets}
        if name in by_q:
            return name
        flat = {t.qualname.replace(":", "."): t.qualname for t in targets}
        if name.replace(":", ".") in flat:
            return flat[name.replace(":", ".")]
        tail = name.replace(":", ".").split(".")
        for t in targets:
            parts = t.qualname.replace(":", ".").split(".")
            if parts[-len(tail):] == tail or t.name == name:
                return t.qualname
        return None

    async def _synthesize(self, experiments: list[Experiment]) -> None:
        await self.stage("probes", "start", model=ROSTER["lightning"].label, count=len(experiments))
        research = render_notes(self.research)

        async def one(e: Experiment) -> None:
            t = e.target
            context = f"\nResearch notes:\n{_truncate(research, 3000)}\n" if research and t.status == "dependency" else ""
            user = prompts.PROBE_USER.format(
                qualname=t.qualname,
                import_line=e.import_line(),
                kind=t.kind,
                sig_a=t.signature_a or "(absent)",
                sig_b=t.signature_b or "(absent)",
                focus=e.focus,
                hypotheses="\n".join(f"- {h}" for h in e.hypotheses) or "- (none)",
                source_a=_truncate(t.source_a or "# does not exist before the PR", 6000),
                source_b=_truncate(t.source_b or "# removed by the PR", 6000),
                context=context,
            )
            try:
                text = await self.llm.chat(
                    "lightning",
                    [{"role": "system", "content": prompts.PROBE_SYSTEM}, {"role": "user", "content": user}],
                    purpose=f"probe {e.id}",
                    max_tokens=4500,
                    temperature=0.5,
                )
                e.code = extract_code(text)
                if _syntax_error(e.code):
                    e.code = await self._regenerate(e, f"The previous probe did not compile: {_syntax_error(e.code)}. It was probably too long. Write a shorter one.")
            except LLMError as err:
                e.error = str(err)
            await self.bus.emit("probe", id=e.id, target=t.qualname, code=e.code, error=e.error)

        await asyncio.gather(*(one(e) for e in experiments if not e.code))
        for e in experiments:
            if e.code and e.focus.startswith("Witness calls"):
                await self.bus.emit("probe", id=e.id, target=e.target.qualname, code=e.code, error=None)
        await self.stage("probes", "end", count=sum(1 for e in experiments if e.code))

    async def _regenerate(self, e: Experiment, error: str) -> str:
        t = e.target
        user = prompts.PROBE_USER.format(
            qualname=t.qualname,
            import_line=e.import_line(),
            kind=t.kind,
            sig_a=t.signature_a or "(absent)",
            sig_b=t.signature_b or "(absent)",
            focus=e.focus,
            hypotheses="\n".join(f"- {h}" for h in e.hypotheses) or "- (none)",
            source_a=_truncate(t.source_a or "# does not exist before the PR", 6000),
            source_b=_truncate(t.source_b or "# removed by the PR", 6000),
            context=f"\nA previous probe for this target failed with:\n{error[:800]}\nKeep run(case) and cases() consistent with each other.\n",
        )
        text = await self.llm.chat(
            "lightning",
            [{"role": "system", "content": prompts.PROBE_SYSTEM}, {"role": "user", "content": user}],
            purpose=f"regenerate {e.id}",
            max_tokens=4500,
            temperature=0.3,
        )
        await self.bus.emit("repair", id=e.id, error="regenerated after failed repair")
        return extract_code(text)

    async def _repaired_or_regenerated(self, e: Experiment, error: str) -> str:
        code = await self._repair(e, error)
        if _syntax_error(code):
            code = await self._regenerate(e, error)
        return code

    async def _repair(self, e: Experiment, error: str) -> str:
        user = (
            f"Target: {e.target.qualname}\nImport with: {e.import_line()}\nSignature: {e.target.signature_b or e.target.signature_a}\n\n"
            f"Failure:\n{error}\n\nProbe:\n```python\n{e.code}\n```\n\n"
            f"Target source:\n```python\n{_truncate(e.target.source_b or e.target.source_a, 5000)}\n```"
        )
        text = await self.llm.chat(
            "nano",
            [{"role": "system", "content": prompts.REPAIR_SYSTEM}, {"role": "user", "content": user}],
            purpose=f"repair {e.id}",
            max_tokens=3000,
            temperature=0.2,
        )
        e.repaired = True
        await self.bus.emit("repair", id=e.id, error=error[:600])
        return extract_code(text)

    async def _run_probe(self, e: Experiment) -> None:
        probe = [{"id": e.id, "code": e.code}]
        timeout = settings.probe_timeout_s + 10
        sem = self._exec_sem

        async def go(label: str) -> dict[str, Any]:
            async with sem:
                return await self.executor.run(self.universes[label], probe, timeout)

        labels = ["B"] if e.mode == "solo" else ["A", "A", "B"]
        docs = await asyncio.gather(*(go(lb) for lb in labels), return_exceptions=True)
        for d in docs:
            if isinstance(d, Exception):
                raise d
        if e.mode == "solo":
            e.docs = {"B": docs[0]}
        else:
            e.docs = {"A": docs[0], "A2": docs[1], "B": docs[2]}

    def _probe_broken(self, e: Experiment) -> str | None:
        """Probe bugs show up identically in both universes. Real behavior changes do not."""
        pb = e.docs["B"]["probes"][0]
        pa = e.docs.get("A", {"probes": [{}]})["probes"][0]
        if e.mode == "solo":
            if pb.get("load_error"):
                return f"{pb['load_error']['exc_type']}: {pb['load_error']['exc_msg']}\n{pb['load_error'].get('trace', '')}"
            cases = pb.get("cases", [])
        else:
            la, lb = pa.get("load_error"), pb.get("load_error")
            if la and lb:
                where = "project" if la.get("origin") == "project" and lb.get("origin") == "project" else "probe"
                return f"{la['exc_type']}: {la['exc_msg']} [raised in {where} code]\n{la.get('trace', '')}"
            if la or lb:
                return None
            cases = pa.get("cases", []) + pb.get("cases", [])
        if not cases:
            return "cases() produced no inputs"
        raised = [c for c in cases if c.get("status") == "raised"]
        harness_errors = {"TypeError", "NameError", "AttributeError", "ImportError", "ModuleNotFoundError"}
        if len(raised) == len(cases) and {c.get("exc_type") for c in raised} <= harness_errors:
            c = raised[0]
            return f"every case raised {c.get('exc_type')}: {c.get('exc_msg')} (case {c.get('case')})"
        return None

    def _environmental(self, error: str) -> bool:
        """A missing module inside the project itself means the tree is not importable as checked out."""
        import re as _re

        m = _re.search(r"No module named '([\w.]+)'", error)
        if not m or "[raised in project code]" not in error:
            return False
        top = m.group(1).split(".")[0]
        roots = [self.subject.root_a, self.subject.root_a / "src", self.subject.root_b, self.subject.root_b / "src"]
        return "." in m.group(1) and any((r / top).is_dir() for r in roots)

    async def _execute(self, experiments: list[Experiment]) -> None:
        await self.stage("calibrate", "start")
        await self.stage("execute", "start", executor=self.executor.name)
        self._exec_sem = asyncio.Semaphore(settings.exec_concurrency)

        async def one(e: Experiment) -> None:
            if not e.code:
                return
            try:
                await self._run_probe(e)
                broken = self._probe_broken(e)
                if broken and self._environmental(broken):
                    raise EnvironmentProblem(broken.splitlines()[0])
                if broken:
                    e.code = await self._repaired_or_regenerated(e, broken)
                    await self._run_probe(e)
                    broken = self._probe_broken(e)
                if broken:
                    # Cheap repair did not take. Ask the probe writer for a fresh probe with the failure in view.
                    e.code = await self._regenerate(e, broken)
                    await self._run_probe(e)
                    if self._probe_broken(e):
                        e.error = "probe could not be made to run against this code"
            except EnvironmentProblem as err:
                e.error = f"environment: {err}"
                await self.log(f"{e.id}: the project cannot be imported in this environment ({err}). Skipping repairs.")
            except (SandboxError, LLMError) as err:
                e.error = str(err)[:800]
            payload: dict[str, Any] = {"id": e.id, "target": e.target.qualname, "error": e.error}
            if e.docs and not e.error:
                diffs, stats = compare(
                    e.docs.get("A", {"probes": []}), e.docs["B"], e.docs.get("A2"),
                    {e.id} if e.mode == "solo" else set(),
                )
                st = stats.get(e.id)
                e.stats = st
                if st:
                    payload.update(cases=st.cases, agree=st.agree, diverge=st.diverge, flaky=st.flaky)
                    payload["timeline"] = [
                        {"i": d.index, "kind": d.kind} for d in diffs
                    ]
            await self.bus.emit("execution", **payload)

        await asyncio.gather(*(one(e) for e in experiments))
        flaky = sum(e.stats.flaky for e in self.experiments if e.stats)
        await self.stage("calibrate", "end", flaky=flaky)
        await self.stage("execute", "end", probes=sum(1 for e in experiments if e.stats))

    async def _analyse(self) -> None:
        await self.stage("compare", "start", model=ROSTER["super"].label)
        all_diffs = []
        stats: dict[str, ProbeStats] = {}
        for e in self.experiments:
            if not e.docs or e.error:
                continue
            diffs, st = compare(
                e.docs.get("A", {"probes": []}), e.docs["B"], e.docs.get("A2"), {e.id} if e.mode == "solo" else set()
            )
            all_diffs.extend(diffs)
            stats.update(st)
        self.stats = stats
        self._diffs = all_diffs
        targets_by_probe = {e.id: e.target.qualname for e in self.experiments}
        previous = {(c.probe_id, c.kind, c.examples[0]["case"]): c.explanation for c in self.clusters}
        self.clusters = cluster(all_diffs, targets_by_probe, stats)
        by_id = {e.id: e for e in self.experiments}

        async def explain(c: Cluster) -> None:
            cached = previous.get((c.probe_id, c.kind, c.examples[0]["case"]))
            if cached:
                c.explanation = cached
                return
            e = by_id[c.probe_id]
            user = (
                f"Function: {c.target}\nDifference kind: {c.kind}\n"
                f"{c.count} of {c.total} probed inputs behaved differently. Examples:\n"
                + "\n".join(f"[{i}] input {x['case']}\n  A: {x['a']}\n  B: {x['b']}" for i, x in enumerate(c.examples))
                + f"\n\nBefore:\n```python\n{_truncate(e.target.source_a, 4000)}\n```\n"
                f"After:\n```python\n{_truncate(e.target.source_b, 4000)}\n```"
            )
            try:
                c.explanation = await self.llm.json(
                    "super", prompts.EXPLAIN_SYSTEM, user, purpose=f"explain {c.id}", max_tokens=900
                )
            except LLMError:
                c.explanation = {
                    "title": f"{c.kind.replace('_', ' ')} change in {c.target.split(':')[-1]}",
                    "before": c.examples[0]["a"],
                    "after": c.examples[0]["b"],
                    "summary": "",
                    "category": "regression",
                    "severity": "medium",
                }
            c.severity = str(c.explanation.get("severity", "medium"))
            best = c.explanation.get("best_example")
            if isinstance(best, int) and 0 < best < len(c.examples):
                c.examples.insert(0, c.examples.pop(best))

        async def split(c: Cluster) -> list[Cluster]:
            """Break one function-level cluster into its distinct root causes."""
            e = by_id[c.probe_id]
            user = (
                f"Function: {c.target}\nDifference kind: {c.kind}\nInputs that behaved differently:\n"
                + "\n".join(f"[{i}] input {m['case']}\n  A: {m['a']}\n  B: {m['b']}" for i, m in enumerate(c.members))
                + f"\n\nBefore:\n```python\n{_truncate(e.target.source_a, 4000)}\n```\n"
                f"After:\n```python\n{_truncate(e.target.source_b, 4000)}\n```"
            )
            try:
                data = await self.llm.json("super", prompts.SPLIT_SYSTEM, user, purpose=f"split {c.id}", max_tokens=2500, require="groups")
            except LLMError:
                return [c]
            used: set[int] = set()
            out: list[Cluster] = []
            for g in data.get("groups", []):
                idx = [i for i in g.get("members", []) if isinstance(i, int) and 0 <= i < len(c.members) and i not in used]
                if not idx:
                    continue
                used.update(idx)
                best = g.get("best_example")
                if isinstance(best, int) and best in idx:
                    idx.remove(best)
                    idx.insert(0, best)
                mem = [c.members[i] for i in idx]
                out.append(
                    Cluster(
                        id=c.id,
                        probe_id=mem[0]["probe"],
                        target=c.target,
                        kind=c.kind,
                        count=len(mem),
                        total=c.total,
                        examples=[{k: m[k] for k in ("case", "a", "b", "index")} for m in mem[:8]],
                        members=mem,
                        explanation={k: g.get(k) for k in ("title", "before", "after", "summary", "category", "severity")},
                        severity=str(g.get("severity") or "medium"),
                    )
                )
            rest = [m for i, m in enumerate(c.members) if i not in used]
            if rest and out:
                out[-1].members.extend(rest)
                out[-1].count += len(rest)
            return out or [c]

        to_split = [c for c in self.clusters if c.count >= 3 and c.kind in ("value", "raise_vs_return", "exception_message", "stdout")]
        singles = [c for c in self.clusters if c not in to_split]
        pieces = await asyncio.gather(*(split(c) for c in to_split))
        await asyncio.gather(*(explain(c) for c in singles))
        merged = singles + [p for ps in pieces for p in ps]
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        merged.sort(key=lambda c: (rank.get(c.severity, 2), -c.count))
        for n, c in enumerate(merged, start=1):
            c.id = f"D{n}"
        self.clusters = merged
        for c in merged:
            await self.bus.emit("divergence", **c.to_dict())
        await self.stage("compare", "end", clusters=len(self.clusters), cases=sum(s.cases for s in stats.values()))

    async def _verdict(self, final: bool) -> None:
        await self.stage("verdict", "start", model=ROSTER["ultra"].label)
        exp_lines = []
        for e in self.experiments:
            st = e.stats
            line = {
                "probe": e.id,
                "target": e.target.qualname,
                "mode": e.mode,
                "claims": e.claims,
                "focus": e.focus,
                "cases": st.cases if st else 0,
                "diverged": st.diverge if st else 0,
                "error": e.error,
            }
            if st and st.speed():
                line["timing_b_over_a"] = st.speed()
            if st and st.agreements:
                line["agreements_sample"] = st.agreements[:10]
            if st and st.solo:
                line["solo_observations"] = st.solo[:16]
            exp_lines.append(line)
        clusters = [
            {
                "id": c.id,
                "target": c.target,
                "kind": c.kind,
                "count": f"{c.count}/{c.total}",
                "explanation": c.explanation,
                "examples": c.examples[:4],
            }
            for c in self.clusters
        ]
        user = (
            f"PR intent: {self.intent}\n\nClaims:\n{json.dumps(self.claims, indent=1)}\n\n"
            f"Experiments:\n{json.dumps(exp_lines, indent=1)}\n\n"
            f"Divergence clusters:\n{json.dumps(clusters, indent=1) if clusters else '(none: A and B agreed on every probed input)'}\n\n"
            f"Project test suite (pytest) per universe: {json.dumps(self._suite_summary()) if self.suites else 'no test suite found'}\n\n"
            f"Overall timing, geometric mean of B/A call time over agreeing inputs: {json.dumps(self._speed())}\n\n"
            f"Targets available for follow-up: {[t.qualname for t in (self.diff.targets if self.diff else [])]}"
        )
        data = await self.llm.json("ultra", prompts.VERDICT_SYSTEM, user, purpose="verdict", max_tokens=5000, require="ledger")
        claim_ids = {c["id"] for c in self.claims}
        ledger = []
        got = {str(x.get("claim")): x for x in data.get("ledger", []) if isinstance(x, dict)}
        for c in self.claims:
            x = got.get(c["id"], {})
            status = x.get("status") if x.get("status") in ("confirmed", "contradicted", "unverified") else "unverified"
            if not c["testable"] and status != "contradicted":
                status = "untestable"
            ledger.append(
                {
                    "claim": c["id"],
                    "status": status,
                    "evidence": [ev for ev in x.get("evidence", []) if isinstance(ev, str)],
                    "rationale": str(x.get("rationale", "")),
                }
            )
        self.ledger = ledger
        dv = {str(x.get("id")): x for x in data.get("divergences", []) if isinstance(x, dict)}
        for c in self.clusters:
            x = dv.get(c.id, {})
            decl = x.get("declared_by")
            c.declared_by = decl if decl in claim_ids else None
            sev = x.get("severity")
            if sev in SEVERITY_RANK:
                c.severity = sev
            c.rationale = str(x.get("rationale", ""))
        self._follow_ups = [f for f in data.get("follow_up", []) if isinstance(f, dict)] if not final else []
        self.verdict = self._decide(str(data.get("headline", "")), str(data.get("summary", "")))
        await self.bus.emit("ledger", ledger=self.ledger, verdict=self.verdict,
                            divergences=[c.to_dict() for c in self.clusters], final=final)
        await self.stage("verdict", "end", label=self.verdict["label"])

    def _speed(self) -> dict[str, Any] | None:
        pairs = [p for s in self.stats.values() for p in s.timing]
        return ProbeStats("all", timing=pairs).speed()

    def _suite_summary(self) -> dict[str, Any]:
        keys = ("ran", "passed", "failed", "errors", "skipped", "summary")
        return {k: {x: v.get(x) for x in keys} for k, v in self.suites.items()}

    def _make_follow_ups(self, rnd: int) -> list[Experiment]:
        kinds = {c["id"]: c["kind"] for c in self.claims}
        unverified = {
            x["claim"] for x in self.ledger
            if x["status"] == "unverified" and kinds.get(x["claim"]) not in ("performance", "tests")
        }
        by_q = {t.qualname: t for t in (self.diff.targets if self.diff else [])}
        added = []
        for f in self._follow_ups:
            q = str(f.get("target", ""))
            claim = str(f.get("claim", ""))
            if q not in by_q or claim not in unverified:
                continue
            t = by_q[q]
            e = Experiment(
                id=f"P{len(self.experiments) + 1}",
                target=t,
                mode="solo" if t.source_a is None else "twin",
                claims=[claim],
                focus=str(f.get("focus", "")),
                hypotheses=[str(f.get("focus", ""))],
                round=rnd,
            )
            self.experiments.append(e)
            added.append(e)
            if len(added) >= 4:
                break
        self._follow_ups = []
        return added

    def _decide(self, headline: str, summary: str) -> dict[str, Any]:
        kinds = {c["id"]: c["kind"] for c in self.claims}
        # Suite counts and timings depend on the machine. A miss there earns review, not an inconsistent verdict.
        soft = {"tests", "performance"}
        contradicted = [x for x in self.ledger if x["status"] == "contradicted" and kinds.get(x["claim"]) not in soft]
        soft_misses = [x for x in self.ledger if x["status"] == "contradicted" and kinds.get(x["claim"]) in soft]
        confirmed = [x for x in self.ledger if x["status"] == "confirmed"]
        unverified = [x for x in self.ledger if x["status"] == "unverified"]
        undeclared = [c for c in self.clusters if not c.declared_by]
        serious = [c for c in undeclared if SEVERITY_RANK.get(c.severity, 1) >= 2]
        ran = [e for e in self.experiments if e.stats and e.stats.cases]
        if self.diff and self.diff.targets and not ran:
            # Nothing executed, so nothing was observed. Refuse to judge the PR on that.
            label = "inconclusive"
        elif contradicted or serious:
            label = "inconsistent"
        elif undeclared or unverified or soft_misses:
            label = "needs_review"
        else:
            label = "consistent"
        cases = sum(s.cases for s in self.stats.values())
        return {
            "label": label,
            "headline": headline,
            "summary": summary,
            "counts": {
                "claims": len(self.claims),
                "confirmed": len(confirmed),
                "contradicted": len(contradicted) + len(soft_misses),
                "unverified": len(unverified),
                "undeclared": len(undeclared),
                "declared": len(self.clusters) - len(undeclared),
                "serious": len(serious),
                "probes": sum(1 for e in self.experiments if e.stats),
                "cases": cases,
                "diverging_cases": sum(s.diverge for s in self.stats.values()),
                "flaky_discarded": sum(s.flaky for s in self.stats.values()),
            },
            "speed": self._speed(),
            "suites": self._suite_summary(),
        }

    def result(self) -> dict[str, Any]:
        res = {
            "id": self.subject.id,
            "version": 1,
            "created_at": self._t0,
            "duration": round(time.time() - self._t0, 2),
            "subject": self.subject.public(),
            "executor": self.executor.name,
            "universes": {k: v.meta for k, v in self.universes.items()},
            "roster": {k: {"id": v.id, "label": v.label, "role": v.role} for k, v in ROSTER.items()},
            "diff": {**(self.diff.summary() if self.diff else {}), "unified": _truncate(self.diff.unified_diff if self.diff else "", 150_000)},
            "intent": self.intent,
            "claims": self.claims,
            "research": self.research,
            "suites": self.suites,
            "experiments": [e.to_dict() for e in self.experiments],
            "divergences": [c.to_dict() for c in self.clusters],
            "ledger": self.ledger,
            "verdict": self.verdict,
            "meter": self.meter.to_dict(),
        }
        res["artifacts"] = {
            "markdown": build_markdown(res),
            "pinned_tests": build_pinned_tests(res, self.experiments),
        }
        return res
