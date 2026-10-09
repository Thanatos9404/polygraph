"""Case-by-case comparison of universe outputs, calibration against noise, and clustering."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Outcome:
    status: str  # ok | raised | timeout | load_error | missing
    value: str | None = None
    exc_type: str | None = None
    exc_msg: str | None = None
    stdout: str = ""

    @classmethod
    def from_case(cls, c: dict[str, Any]) -> "Outcome":
        return cls(
            status=c.get("status", "missing"),
            value=c.get("value"),
            exc_type=c.get("exc_type"),
            exc_msg=c.get("exc_msg"),
            stdout=c.get("stdout", ""),
        )

    def short(self) -> str:
        if self.status == "ok":
            return self.value or "None"
        if self.status == "raised":
            return f"raises {self.exc_type}: {self.exc_msg}" if self.exc_msg else f"raises {self.exc_type}"
        if self.status == "load_error":
            return f"probe cannot load: {self.exc_type}: {self.exc_msg}"
        return self.status


def diff_kind(a: Outcome, b: Outcome) -> str | None:
    if a.status != b.status:
        if "load_error" in (a.status, b.status):
            return "load"
        if "timeout" in (a.status, b.status):
            return "timeout"
        return "raise_vs_return"
    if a.status == "raised":
        if a.exc_type != b.exc_type:
            return "exception_type"
        if a.exc_msg != b.exc_msg:
            return "exception_message"
        return None
    if a.status == "ok":
        if a.value != b.value:
            return "value"
        if a.stdout != b.stdout:
            return "stdout"
    if a.status == "load_error" and (a.exc_type, a.exc_msg) != (b.exc_type, b.exc_msg):
        return "load"
    return None


@dataclass
class CaseDiff:
    probe_id: str
    index: int
    case: str
    kind: str
    a: Outcome
    b: Outcome


@dataclass
class ProbeStats:
    probe_id: str
    cases: int = 0
    agree: int = 0
    diverge: int = 0
    flaky: int = 0
    load_error_a: str | None = None
    load_error_b: str | None = None
    agreements: list[dict[str, str]] = field(default_factory=list)
    solo: list[dict[str, str]] = field(default_factory=list)
    timing: list[tuple[float, float]] = field(default_factory=list)  # (A us, B us) per agreeing input

    def speed(self) -> dict | None:
        """Geometric mean of B/A call time over inputs where both universes agreed."""
        pairs = [(a, b) for a, b in self.timing if a > 0 and b > 0]
        if len(pairs) < 3:
            return None
        ratio = math.exp(sum(math.log(b / a) for a, b in pairs) / len(pairs))
        return {
            "inputs": len(pairs),
            "ratio": round(ratio, 3),
            "a_median_us": round(statistics.median(a for a, _ in pairs), 2),
            "b_median_us": round(statistics.median(b for _, b in pairs), 2),
        }


@dataclass
class Cluster:
    id: str
    probe_id: str
    target: str
    kind: str
    count: int
    total: int
    examples: list[dict[str, str]]
    explanation: dict[str, Any] = field(default_factory=dict)
    members: list[dict[str, str]] = field(default_factory=list)
    declared_by: str | None = None
    severity: str = "medium"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("members", None)
        return d


def _index(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in doc.get("probes", [])}


def compare(
    doc_a: dict[str, Any],
    doc_b: dict[str, Any],
    doc_a2: dict[str, Any] | None,
    solo_ids: set[str],
) -> tuple[list[CaseDiff], dict[str, ProbeStats]]:
    """Align A, B and the calibration run A2. Cases where A disagrees with A2 are noise and are dropped."""
    ia, ib = _index(doc_a), _index(doc_b)
    ia2 = _index(doc_a2) if doc_a2 else {}
    diffs: list[CaseDiff] = []
    stats: dict[str, ProbeStats] = {}
    for pid in sorted(set(ia) | set(ib)):
        st = stats.setdefault(pid, ProbeStats(pid))
        pa, pb = ia.get(pid, {}), ib.get(pid, {})
        if pa.get("load_error"):
            st.load_error_a = f"{pa['load_error']['exc_type']}: {pa['load_error']['exc_msg']}"
        if pb.get("load_error"):
            st.load_error_b = f"{pb['load_error']['exc_type']}: {pb['load_error']['exc_msg']}"

        if pid in solo_ids:
            for c in pb.get("cases", []):
                st.cases += 1
                st.solo.append({"case": c.get("case", ""), "outcome": Outcome.from_case(c).short()})
            continue

        if pa.get("load_error") or pb.get("load_error"):
            la, lb = pa.get("load_error"), pb.get("load_error")
            oa = Outcome("load_error", exc_type=la["exc_type"], exc_msg=la["exc_msg"]) if la else Outcome("ok", value="loads")
            ob = Outcome("load_error", exc_type=lb["exc_type"], exc_msg=lb["exc_msg"]) if lb else Outcome("ok", value="loads")
            kind = diff_kind(oa, ob)
            if kind and not (la and lb):
                diffs.append(CaseDiff(pid, -1, "<import>", "load", oa, ob))
                st.diverge += 1
            continue

        cases_a, cases_b = pa.get("cases", []), pb.get("cases", [])
        cases_a2 = ia2.get(pid, {}).get("cases", []) if ia2 else []
        for i in range(max(len(cases_a), len(cases_b))):
            ca = cases_a[i] if i < len(cases_a) else None
            cb = cases_b[i] if i < len(cases_b) else None
            if ca is None or cb is None or ca.get("case") != cb.get("case"):
                continue
            st.cases += 1
            oa, ob = Outcome.from_case(ca), Outcome.from_case(cb)
            if i < len(cases_a2) and cases_a2[i].get("case") == ca.get("case"):
                if diff_kind(oa, Outcome.from_case(cases_a2[i])) is not None:
                    st.flaky += 1
                    continue
            kind = diff_kind(oa, ob)
            if kind is None:
                st.agree += 1
                a_us = [x for x in (ca.get("us"), (cases_a2[i] if i < len(cases_a2) else {}).get("us")) if x]
                if a_us and cb.get("us"):
                    st.timing.append((min(a_us), cb["us"]))
                if len(st.agreements) < 14:
                    st.agreements.append({"case": ca.get("case", ""), "outcome": oa.short()})
            else:
                st.diverge += 1
                diffs.append(CaseDiff(pid, i, ca.get("case", ""), kind, oa, ob))
    return diffs, stats


def cluster(diffs: list[CaseDiff], targets_by_probe: dict[str, str], stats: dict[str, ProbeStats]) -> list[Cluster]:
    # Two probes of the same function that trip the same change produce one finding, not two.
    groups: dict[tuple, list[CaseDiff]] = {}
    for d in diffs:
        target = targets_by_probe.get(d.probe_id, d.probe_id)
        if d.kind in ("exception_type", "raise_vs_return"):
            key = (target, d.kind, d.a.exc_type, d.b.exc_type)
        elif d.kind == "exception_message":
            key = (target, d.kind, d.a.exc_type)
        else:
            key = (target, d.kind)
        groups.setdefault(key, []).append(d)
    clusters: list[Cluster] = []
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0]))
    for n, (key, items) in enumerate(ordered, start=1):
        items.sort(key=lambda d: (len(d.case), d.index))
        # De-duplicate identical witnesses found by different probes.
        seen_cases: set[str] = set()
        unique = []
        for d in items:
            if d.case not in seen_cases:
                seen_cases.add(d.case)
                unique.append(d)
        items = unique
        pid = items[0].probe_id
        clusters.append(
            Cluster(
                id=f"D{n}",
                probe_id=pid,
                target=key[0],
                kind=key[1],
                count=len(items),
                total=sum(stats[p].cases for p, t in targets_by_probe.items() if t == key[0] and p in stats) or len(items),
                examples=[
                    {"case": d.case, "a": d.a.short(), "b": d.b.short(), "index": str(d.index)} for d in items[:8]
                ],
                members=[
                    {"case": d.case, "a": d.a.short(), "b": d.b.short(), "index": str(d.index), "probe": d.probe_id}
                    for d in items[:48]
                ],
            )
        )
    return clusters
