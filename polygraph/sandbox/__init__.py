"""Execution backends. Each one turns a source tree into a universe that can run probes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

HARNESS_PATH = Path(__file__).resolve().parent.parent / "harness.py"
BEGIN = "<<<POLYGRAPH-BEGIN>>>"
END = "<<<POLYGRAPH-END>>>"


class SandboxError(RuntimeError):
    pass


@dataclass
class Universe:
    label: str  # "A" (base) or "B" (head)
    root: Path
    requirements: str | None = None
    backend_ref: Any = None  # interpreter path for local, image handle for Token Factory Sandboxes
    meta: dict[str, Any] = field(default_factory=dict)


class Executor(Protocol):
    name: str

    async def prepare(self, label: str, root: Path, requirements: str | None) -> Universe: ...

    async def run(self, universe: Universe, probes: list[dict[str, Any]], timeout: int) -> dict[str, Any]: ...

    async def run_suite(self, universe: Universe, timeout: int) -> dict[str, Any]: ...

    async def close(self) -> None: ...


PYTEST_ARGS = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "-W", "ignore"]


def install_spec(root: Path) -> str | None:
    """Editable install target for a buildable project, with any test extras, or None for plain source trees."""
    pp = root / "pyproject.toml"
    extras: list[str] = []
    buildable = (root / "setup.py").exists()
    if pp.exists():
        import tomllib

        try:
            data = tomllib.loads(pp.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
        buildable = buildable or "build-system" in data or "project" in data
        opt = data.get("project", {}).get("optional-dependencies", {}) or {}
        extras = [k for k in opt if "test" in k.lower()][:2]
    if not buildable:
        return None
    return f"{root.as_posix()}[{','.join(extras)}]" if extras else root.as_posix()


# Builds that derive their version from git metadata need a stand-in when the tree has no .git.
BUILD_ENV = {
    "SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0",
    "HATCH_VCS_PRETEND_VERSION": "0.0.0",
    "PDM_BUILD_SCM_VERSION": "0.0.0",
}


def has_tests(root: Path) -> bool:
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if any(part.startswith(".") or part in ("node_modules", "venv", ".venv") for part in rel.split("/")):
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            return True
    return False


def parse_pytest(code: int, out: str, seconds: float) -> dict[str, Any]:
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    counts = {k: 0 for k in ("passed", "failed", "errors", "skipped")}
    for n, word in re.findall(r"(\d+) (passed|failed|errors?|skipped)", tail):
        counts["errors" if word.startswith("error") else word] = int(n)
    return {
        "ran": True,
        "exit_code": code,
        **counts,
        "summary": tail[-200:],
        "tail": out[-1200:],
        "seconds": round(seconds, 2),
    }


def parse_harness_output(stdout: str, stderr: str = "") -> dict[str, Any]:
    if BEGIN not in stdout or END not in stdout:
        tail = (stderr or stdout)[-1500:]
        raise SandboxError(f"harness produced no result block. Output tail:\n{tail}")
    body = stdout.split(BEGIN, 1)[1].split(END, 1)[0]
    return json.loads(body)


def get_executor(name: str) -> Executor:
    if name == "nebius":
        from .nebius import NebiusSandboxExecutor

        return NebiusSandboxExecutor()
    from .local import LocalExecutor

    return LocalExecutor()
