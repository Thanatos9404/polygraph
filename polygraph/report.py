"""Artifacts a reviewer can use directly: a PR comment and a pytest file that pins every finding."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .llm import clean_text
from .sandbox import HARNESS_PATH

if TYPE_CHECKING:
    from .engine import Experiment

LABELS = {
    "consistent": "Consistent",
    "needs_review": "Needs review",
    "inconsistent": "Inconsistent",
    "inconclusive": "Inconclusive",
}
STATUS = {
    "confirmed": "Confirmed",
    "contradicted": "Contradicted",
    "unverified": "Unverified",
    "untestable": "Not testable",
}


def _cell(text: str, limit: int = 120) -> str:
    text = (text or "").replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_markdown(res: dict[str, Any]) -> str:
    v = res.get("verdict", {})
    counts = v.get("counts", {})
    claims = {c["id"]: c for c in res.get("claims", [])}
    lines = [
        f"## Polygraph: {LABELS.get(v.get('label', ''), 'No verdict')}",
        "",
        f"**{v.get('headline', '')}**",
        "",
        v.get("summary", ""),
        "",
        "### Claim ledger",
        "",
        "| | Claim | Result | Evidence |",
        "|---|---|---|---|",
    ]
    for x in res.get("ledger", []):
        c = claims.get(x["claim"], {})
        stmt = c.get("statement", "") + (" *(implied)*" if c.get("implicit") else "")
        lines.append(
            f"| {x['claim']} | {_cell(stmt)} | {STATUS.get(x['status'], x['status'])} | {_cell(x.get('rationale', ''), 160)} |"
        )
    undeclared = [d for d in res.get("divergences", []) if not d.get("declared_by")]
    declared = [d for d in res.get("divergences", []) if d.get("declared_by")]
    if undeclared:
        lines += ["", f"### Undeclared behavior changes ({len(undeclared)})", ""]
        for d in undeclared:
            ex = d["examples"][0]
            title = d.get("explanation", {}).get("title") or d["kind"]
            lines += [
                f"**{d['id']} · {title}** · `{d['target']}` · severity {d.get('severity', 'medium')} · {d['count']}/{d['total']} inputs",
                "",
                f"- input: `{_cell(ex['case'], 200)}`",
                f"- before: `{_cell(ex['a'], 200)}`",
                f"- after: `{_cell(ex['b'], 200)}`",
            ]
            if d.get("explanation", {}).get("summary"):
                lines.append(f"- {d['explanation']['summary']}")
            lines.append("")
    if declared:
        lines += ["", "### Declared changes observed", ""]
        for d in declared:
            title = d.get("explanation", {}).get("title") or d["kind"]
            lines.append(f"- **{d['id']}** {title} (declared by {d['declared_by']}), {d['count']}/{d['total']} inputs")
    meter = res.get("meter", {})
    lines += [
        "",
        "---",
        f"{counts.get('probes', 0)} probes · {counts.get('cases', 0)} inputs run in both universes · "
        f"{counts.get('flaky_discarded', 0)} noisy inputs discarded by calibration · "
        f"${meter.get('total_cost', 0):.4f} on Nebius Token Factory with NVIDIA Nemotron",
    ]
    return clean_text("\n".join(lines).strip() + "\n")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:48] or "case"


def build_pinned_tests(res: dict[str, Any], experiments: list["Experiment"]) -> str:
    """One test per divergence. Undeclared changes are pinned to base behavior, so the test fails on the PR."""
    by_id = {e.id: e for e in experiments}
    probes: dict[str, str] = {}
    tests: list[str] = []
    for d in res.get("divergences", []):
        e = by_id.get(d["probe_id"])
        if not e or not e.docs or d["kind"] == "load":
            continue
        idx = int(d["examples"][0]["index"])
        side = "B" if d.get("declared_by") else "A"
        doc = e.docs.get(side) or {}
        cases = (doc.get("probes") or [{}])[0].get("cases", [])
        if idx < 0 or idx >= len(cases):
            continue
        c = cases[idx]
        expected = {"status": c.get("status"), "value": c.get("value"), "exc_type": c.get("exc_type")}
        probes[e.id] = e.code
        title = d.get("explanation", {}).get("title") or d["kind"]
        why = (
            f"Declared by {d['declared_by']}: pins the new behavior."
            if d.get("declared_by")
            else "Undeclared: passes on the base branch and fails on this PR until the change is declared or reverted."
        )
        tests.append(
            f'def test_{d["id"].lower()}_{_slug(title)}():\n'
            f'    """{title}. {why}"""\n'
            f"    _check({e.id!r}, {idx}, {expected!r})\n"
        )
    if not tests:
        return "# Polygraph found no behavior changes to pin.\n"
    harness = HARNESS_PATH.read_text(encoding="utf-8")
    probe_src = "\n".join(f"PROBES[{k!r}] = {v!r}" for k, v in probes.items())
    header = f'''"""Behavior pinned by Polygraph for: {res["subject"]["title"]}

Generated from run {res["id"]}. Each test replays one probe input and compares the canonical output.
Drop this file into your test suite and run pytest from the project root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HARNESS_SOURCE = {harness!r}
_H = {{"__name__": "polygraph_harness"}}
exec(compile(_HARNESS_SOURCE, "polygraph_harness", "exec"), _H)

PROBES = {{}}
{probe_src}


def _check(probe_id, index, expected):
    ns = {{"__name__": "polygraph_probe"}}
    exec(compile(PROBES[probe_id], probe_id, "exec"), ns)
    _H["random"].seed(1234)
    raw = ns["cases"]() if "cases" in ns else ns["CASES"]
    case = list(raw)[index]
    got = _H["_run_case"](ns["run"], case)
    assert got["status"] == expected["status"], (got, expected)
    if expected["status"] == "ok":
        assert got["value"] == expected["value"], (got["value"], expected["value"])
    if expected["status"] == "raised":
        assert got["exc_type"] == expected["exc_type"], (got["exc_type"], expected["exc_type"])

'''
    return header + "\n\n".join(tests)
