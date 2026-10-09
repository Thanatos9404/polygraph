"""Offline tests: no model calls, no network."""

import asyncio
import json
from pathlib import Path

import pytest

from polygraph.analysis import diff_trees
from polygraph.budget import BudgetExceeded, Caps, Ledger
from polygraph.compare import Outcome, cluster, compare, diff_kind
from polygraph.llm import clean_text, extract_code, extract_json
from polygraph.report import build_markdown
from polygraph.sandbox.local import LocalExecutor

ROOT = Path(__file__).resolve().parent.parent
SCEN = ROOT / "scenarios"


# ---------------------------------------------------------------- static analysis


def test_refactor_targets_public_entry_points():
    d = diff_trees(SCEN / "slugkit-refactor/base", SCEN / "slugkit-refactor/head")
    names = {t.qualname: t.status for t in d.targets}
    assert names["slugkit.core:slugify"] == "changed"
    assert names["slugkit.core:unique_slug"] == "caller"
    assert "slugkit.core:_ascii_fold" not in names  # reached through slugify


def test_dependency_bump_targets_code_that_uses_the_package():
    d = diff_trees(SCEN / "packaging-bump/base", SCEN / "packaging-bump/head")
    assert [(c.package, c.before, c.after) for c in d.dependency_changes] == [("packaging", "==21.3", "==24.1")]
    assert {t.status for t in d.targets} == {"dependency"}
    assert {t.name for t in d.targets} == {"is_compatible", "newest", "sort_versions"}


# ---------------------------------------------------------------- harness and comparison

PROBE = """
from timekit import parse_duration

def cases():
    return ["90s", "", "1h30m", "-5", "2d"]

def run(case):
    return parse_duration(case)
"""


def test_twin_execution_finds_real_divergences(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGRAPH_WORKDIR", str(tmp_path))
    ex = LocalExecutor()

    async def go():
        a = await ex.prepare("A", SCEN / "duration-fix/base", None)
        b = await ex.prepare("B", SCEN / "duration-fix/head", None)
        probe = [{"id": "P1", "code": PROBE}]
        da, da2, db = await asyncio.gather(ex.run(a, probe, 30), ex.run(a, probe, 30), ex.run(b, probe, 30))
        await ex.close()
        return da, da2, db

    da, da2, db = asyncio.run(go())
    diffs, stats = compare(da, db, da2, set())
    by_case = {d.case: d for d in diffs}
    assert stats["P1"].cases == 5 and stats["P1"].flaky == 0
    assert "'90s'" not in by_case  # unchanged behavior agrees
    assert by_case["''"].a.exc_type == "IndexError" and by_case["''"].b.exc_type == "ValueError"
    assert by_case["'1h30m'"].b.value == "5400"
    assert by_case["'-5'"].kind == "raise_vs_return"
    clusters = cluster(diffs, {"P1": "timekit.duration:parse_duration"}, stats)
    assert sum(c.count for c in clusters) == len(diffs)


def test_calibration_discards_noise():
    a = {"probes": [{"id": "P", "cases": [{"case": "1", "status": "ok", "value": "1"}, {"case": "2", "status": "ok", "value": "x"}]}]}
    a2 = {"probes": [{"id": "P", "cases": [{"case": "1", "status": "ok", "value": "1"}, {"case": "2", "status": "ok", "value": "y"}]}]}
    b = {"probes": [{"id": "P", "cases": [{"case": "1", "status": "ok", "value": "2"}, {"case": "2", "status": "ok", "value": "z"}]}]}
    diffs, stats = compare(a, b, a2, set())
    assert [d.case for d in diffs] == ["1"]
    assert stats["P"].flaky == 1


def test_diff_kinds():
    ok = Outcome("ok", value="1")
    assert diff_kind(ok, Outcome("ok", value="1")) is None
    assert diff_kind(ok, Outcome("ok", value="2")) == "value"
    assert diff_kind(ok, Outcome("raised", exc_type="ValueError")) == "raise_vs_return"
    assert diff_kind(Outcome("raised", exc_type="A", exc_msg="x"), Outcome("raised", exc_type="A", exc_msg="y")) == "exception_message"


# ---------------------------------------------------------------- budget


def test_budget_refuses_before_overspending(tmp_path):
    led = Ledger(tmp_path / "b.json", Caps(lifetime_usd=1.0, daily_usd=0.5, run_usd=0.2, tavily_daily_credits=2))
    led.reserve(0.15, run_spent=0.0)
    with pytest.raises(BudgetExceeded):
        led.reserve(0.1, run_spent=0.15)  # per-run cap
    led.settle(0.15, 0.12)
    assert led.snapshot()["today_spent"] == pytest.approx(0.12)
    for _ in range(3):
        led.reserve(0.1, run_spent=0.0)
        led.settle(0.1, 0.1)
    with pytest.raises(BudgetExceeded):
        led.reserve(0.1, run_spent=0.0)  # daily cap: 0.42 + 0.1 > 0.5
    led.take_tavily(2)
    with pytest.raises(BudgetExceeded):
        led.take_tavily(1)
    assert json.loads((tmp_path / "b.json").read_text())["lifetime_usd"] == pytest.approx(0.42)


# ---------------------------------------------------------------- model output parsing


def test_extract_json_handles_reasoning_and_fences():
    assert extract_json('<think>hmm {"no": 1}</think>Sure:\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('prefix {"a": "b}"} suffix') == {"a": "b}"}


def test_extract_code_recovers_unfenced_and_cut_replies():
    assert extract_code("Here you go:\n```python\nimport x\nprint(1)").startswith("import x")
    assert extract_code("Sure.\nfrom a import b\ndef run(c): return c").startswith("from a import b")


def test_clean_text_removes_dashes():
    assert clean_text({"t": ["a — b", "1–3"]}) == {"t": ["a, b", "1-3"]}


# ---------------------------------------------------------------- report


def test_markdown_report_from_recorded_run():
    recorded = sorted((ROOT / "recorded").glob("*.json"))
    if not recorded:
        pytest.skip("no recorded runs")
    res = json.loads(recorded[0].read_text(encoding="utf-8"))["result"]
    md = build_markdown(res)
    assert md.startswith("## Polygraph:")
    assert "Claim ledger" in md
    assert "—" not in md
