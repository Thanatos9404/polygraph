"""The control arm: review a PR by reading it, the way diff-reading reviewers do today.

The same Nemotron model reads the PR text and the diff and predicts which behaviors changed, each with a
concrete call. Polygraph then executes every predicted call in both universes. A prediction is real only if
the two universes actually disagree on it. This measures how often reading alone gets behavior right.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .analysis import diff_trees
from .config import settings
from .llm import TokenFactory
from .sandbox import get_executor
from .compare import Outcome, diff_kind
from .sources import Subject, requirements_for

REVIEW_SYSTEM = """You are a senior code reviewer. You can read the pull request and its diff, but you cannot run anything.
Review it the way you would on GitHub, then list every runtime behavior change you believe this PR introduces, declared or not.

For each predicted change give one concrete call that would demonstrate it, as a single Python expression using only the
project's public functions and literals, plus the import line it needs.

Write plain sentences without em dashes. Reply with JSON only:
{"review": "the review comment you would post, 2 to 5 sentences",
 "approve": true,
 "predicted_changes": [{"description": "...", "import": "from pkg.mod import func", "call": "func('input')", "before": "what it returned before", "after": "what it returns now"}]}"""


def _probe(pred: dict[str, Any], idx: int) -> dict[str, str]:
    imp = str(pred.get("import", "")).strip()
    call = str(pred.get("call", "")).strip()
    code = f"{imp}\n\nCASES = [0]\n\n\ndef run(_case):\n    return {call}\n"
    return {"id": f"B{idx}", "code": code}


async def review(subject: Subject) -> dict[str, Any]:
    diff = diff_trees(subject.root_a, subject.root_b, settings.max_targets)
    llm = TokenFactory()
    user = f"{subject.pr_text()}\n\nDiff:\n{diff.unified_diff[:40000]}"
    data = await llm.json("ultra", REVIEW_SYSTEM, user, purpose="baseline review", max_tokens=4000)
    preds = [p for p in data.get("predicted_changes", []) if isinstance(p, dict) and p.get("call")][:12]

    executor = get_executor("local")
    try:
        ua, ub = await asyncio.gather(
            executor.prepare("A", subject.root_a, requirements_for(subject.root_a)),
            executor.prepare("B", subject.root_b, requirements_for(subject.root_b)),
        )
        probes = [_probe(p, i) for i, p in enumerate(preds, start=1)]
        checked = []
        for p, probe in zip(preds, probes):
            try:
                compile(probe["code"], probe["id"], "exec")
                da, db = await asyncio.gather(executor.run(ua, [probe], 30), executor.run(ub, [probe], 30))
                pa, pb = da["probes"][0], db["probes"][0]
                if pa.get("load_error") or pb.get("load_error") or not pa.get("cases") or not pb.get("cases"):
                    real, a, b = None, (pa.get("load_error") or {}).get("exc_msg", ""), (pb.get("load_error") or {}).get("exc_msg", "")
                else:
                    oa, ob = Outcome.from_case(pa["cases"][0]), Outcome.from_case(pb["cases"][0])
                    real = diff_kind(oa, ob) is not None
                    a, b = oa.short(), ob.short()
            except SyntaxError:
                real, a, b = None, "call does not parse", ""
            checked.append({**p, "real": real, "observed_before": a, "observed_after": b})
    finally:
        await executor.close()

    executable = [c for c in checked if c["real"] is not None]
    return {
        "review": data.get("review", ""),
        "approve": bool(data.get("approve", False)),
        "predictions": checked,
        "executable": len(executable),
        "real": sum(1 for c in executable if c["real"]),
        "cost": llm.meter.total_cost,
    }


if __name__ == "__main__":  # pragma: no cover
    import sys

    from .sources import from_scenario

    out = asyncio.run(review(from_scenario(sys.argv[1])))
    print(json.dumps(out, indent=1))
