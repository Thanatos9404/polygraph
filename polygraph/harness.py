"""In-universe probe runner.

This file is copied verbatim into each universe (a local temp dir or a Token Factory sandbox) and run
with that universe's interpreter. It must stay dependency free and compatible with Python 3.9+.

Usage: python _polygraph_harness.py <code_root> <probes.json>
Prints one JSON document between sentinel lines on the real stdout.
"""

import contextlib
import dataclasses
import datetime
import decimal
import enum
import fractions
import io
import json
import math
import os
import random
import re
import sys
import threading
import time
import traceback
import types

BEGIN = "<<<POLYGRAPH-BEGIN>>>"
END = "<<<POLYGRAPH-END>>>"
MAX_VALUE = 1500
MAX_CASES = 80
CASE_TIMEOUT = float(os.environ.get("POLYGRAPH_CASE_TIMEOUT", "4"))
_ADDR = re.compile(r" at 0x[0-9a-fA-F]+")


def _scrub(text):
    text = _ADDR.sub(" at 0x?", text)
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + "...<truncated>"


def canon(v, depth=0, seen=None):
    """Deterministic, type-preserving text form of a Python value."""
    if seen is None:
        seen = set()
    if depth > 6:
        return "<deep>"
    if v is None or isinstance(v, (bool, int)):
        return repr(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "float(nan)"
        return "float(" + repr(v) + ")"
    if isinstance(v, (str, bytes, bytearray, complex)):
        return repr(v)
    if isinstance(v, (decimal.Decimal, fractions.Fraction, datetime.date, datetime.time, datetime.timedelta)):
        return repr(v)
    if isinstance(v, enum.Enum):
        return type(v).__name__ + "." + str(v.name)
    vid = id(v)
    if vid in seen:
        return "<cycle>"
    seen = seen | {vid}
    if isinstance(v, list):
        return "[" + ", ".join(canon(x, depth + 1, seen) for x in v[:200]) + ("" if len(v) <= 200 else ", ...") + "]"
    if isinstance(v, tuple):
        inner = ", ".join(canon(x, depth + 1, seen) for x in v[:200])
        name = type(v).__name__
        if hasattr(v, "_fields"):
            inner = ", ".join(f + "=" + canon(getattr(v, f), depth + 1, seen) for f in v._fields)
            return name + "(" + inner + ")"
        return "(" + inner + ("," if len(v) == 1 else "") + ")"
    if isinstance(v, (set, frozenset)):
        items = sorted(canon(x, depth + 1, seen) for x in v)
        return type(v).__name__ + "{" + ", ".join(items[:200]) + "}"
    if isinstance(v, dict):
        items = [(canon(k, depth + 1, seen), canon(x, depth + 1, seen)) for k, x in list(v.items())[:200]]
        prefix = "" if type(v) is dict else type(v).__name__
        return prefix + "{" + ", ".join(k + ": " + x for k, x in items) + "}"
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        parts = [f.name + "=" + canon(getattr(v, f.name, None), depth + 1, seen) for f in dataclasses.fields(v)]
        return type(v).__name__ + "(" + ", ".join(parts) + ")"
    if isinstance(v, (types.GeneratorType, map, filter, zip, range, reversed)):
        out = []
        try:
            for i, x in enumerate(v):
                if i >= 200:
                    out.append("...")
                    break
                out.append(canon(x, depth + 1, seen))
        except Exception as e:  # noqa: BLE001
            out.append("<raised " + type(e).__name__ + ">")
        return "iter[" + ", ".join(out) + "]"
    if isinstance(v, type):
        return "<class " + v.__module__ + "." + v.__qualname__ + ">"
    if callable(v) and hasattr(v, "__qualname__"):
        return "<callable " + getattr(v, "__module__", "?") + "." + v.__qualname__ + ">"
    d = getattr(v, "__dict__", None)
    if isinstance(d, dict) and d:
        parts = [k + "=" + canon(x, depth + 1, seen) for k, x in sorted(d.items()) if not k.startswith("__")]
        return type(v).__name__ + "{" + ", ".join(parts[:50]) + "}"
    try:
        return _scrub(repr(v))
    except Exception as e:  # noqa: BLE001
        return "<unrepresentable " + type(v).__name__ + ": " + type(e).__name__ + ">"


def _exc_name(e):
    t = type(e)
    mod = t.__module__
    return t.__qualname__ if mod in ("builtins", "__main__") else mod + "." + t.__qualname__


def _run_case(fn, case):
    box = {}
    buf = io.StringIO()

    def target():
        random.seed(0)
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                box["value"] = fn(case)
        except BaseException as e:  # noqa: BLE001
            box["exc"] = e

    t0 = time.perf_counter()
    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(CASE_TIMEOUT)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    if th.is_alive():
        return {"status": "timeout", "ms": ms, "stdout": ""}
    out = _scrub(buf.getvalue())
    if "exc" in box:
        e = box["exc"]
        return {
            "status": "raised",
            "exc_type": _exc_name(e),
            "exc_msg": _scrub(str(e)),
            "ms": ms,
            "stdout": out,
        }
    try:
        value = _scrub(canon(box.get("value")))
    except Exception as e:  # noqa: BLE001
        value = "<canon failed: " + type(e).__name__ + ">"
    return {"status": "ok", "value": value, "type": type(box.get("value")).__name__, "ms": ms, "stdout": out}


def run_probe(probe):
    ns = {"__name__": "polygraph_probe_" + re.sub(r"\W", "_", probe["id"]), "__file__": os.path.join(os.getcwd(), "_polygraph_probe.py")}
    result = {"id": probe["id"], "cases": []}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(probe["code"], "<probe " + probe["id"] + ">", "exec"), ns)
    except BaseException as e:  # noqa: BLE001
        tb = e.__traceback__
        origin = ""
        while tb is not None:
            origin = tb.tb_frame.f_code.co_filename
            tb = tb.tb_next
        result["load_error"] = {
            "exc_type": _exc_name(e),
            "exc_msg": _scrub(str(e)),
            "trace": _scrub(traceback.format_exc(limit=-4)),
            "origin": "probe" if origin.startswith("<probe") else "project",
        }
        return result
    run = ns.get("run")
    cases_fn = ns.get("cases")
    if not callable(run):
        result["load_error"] = {"exc_type": "ProbeContractError", "exc_msg": "probe defines no run(case)"}
        return result
    try:
        random.seed(1234)
        raw = cases_fn() if callable(cases_fn) else ns.get("CASES", [])
        cases = []
        for i, c in enumerate(raw):
            if i >= MAX_CASES:
                break
            cases.append(c)
    except BaseException as e:  # noqa: BLE001
        result["load_error"] = {"exc_type": _exc_name(e), "exc_msg": _scrub(str(e)), "trace": "cases() failed"}
        return result
    for c in cases:
        obs = _run_case(run, c)
        obs["case"] = _scrub(canon(c))
        if obs["status"] == "ok" and obs["ms"] < 50:
            us = _bench(run, c)
            if us is not None:
                obs["us"] = us
        result["cases"].append(obs)
    return result


def _bench(fn, case, budget=0.015):
    """Average wall time per call in microseconds, measured in a tight loop for about 15 ms."""
    n = 0
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            t0 = time.perf_counter()
            while True:
                fn(case)
                n += 1
                elapsed = time.perf_counter() - t0
                if elapsed >= budget or n >= 5000:
                    break
    except BaseException:  # noqa: BLE001
        return None
    return round(elapsed / n * 1e6, 3)


def main():
    root = os.path.abspath(sys.argv[1])
    with open(sys.argv[2], "r", encoding="utf-8") as fh:
        probes = json.load(fh)
    for p in (os.path.join(root, "src"), root):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(root)
    real_out = sys.__stdout__
    started = time.perf_counter()
    results = [run_probe(p) for p in probes]
    doc = {
        "python": sys.version.split()[0],
        "seconds": round(time.perf_counter() - started, 3),
        "probes": results,
    }
    real_out.write("\n" + BEGIN + "\n" + json.dumps(doc) + "\n" + END + "\n")
    real_out.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
