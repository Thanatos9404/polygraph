"""Local subprocess executor.

Each universe is a separate copy of the source tree, run by its own interpreter. When the tree pins
dependencies, the universe gets a dedicated virtual environment built with uv, cached by content hash,
so base and head can run against different library versions at the same time.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config import settings
from . import BUILD_ENV, PYTEST_ARGS, HARNESS_PATH, SandboxError, Universe, install_spec, parse_harness_output, parse_pytest

_SAFE_ENV = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL", "COMSPEC")


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


class LocalExecutor:
    name = "local"

    def __init__(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="polygraph-harness-", dir=_ensure(settings.workdir / "tmp")))
        self._harness = self._tmp / "_polygraph_harness.py"
        shutil.copyfile(HARNESS_PATH, self._harness)
        self._venv_locks: dict[str, asyncio.Lock] = {}

    async def prepare(self, label: str, root: Path, requirements: str | None) -> Universe:
        python = sys.executable
        meta: dict[str, Any] = {"backend": "local", "python": "host"}
        spec = install_spec(root)
        if spec:
            try:
                python, info = await self._project_venv(label, root, spec, requirements)
                meta.update(info)
                return Universe(label=label, root=root, requirements=requirements, backend_ref=python, meta=meta)
            except SandboxError as e:
                meta["install_warning"] = str(e)[-600:]
        if requirements and requirements.strip():
            python, info = await self._venv_for(requirements)
            meta.update(info)
        return Universe(label=label, root=root, requirements=requirements, backend_ref=python, meta=meta)

    async def _project_venv(self, label: str, root: Path, spec: str, requirements: str | None) -> tuple[str, dict[str, Any]]:
        """A venv of this universe's own, with the project installed editable so generated files and entry points exist."""
        uv = shutil.which("uv")
        if not uv:
            raise SandboxError("uv not found")
        venv = root.parent / f".venv-{label}"
        py = _venv_python(venv)
        env = {**os.environ, **BUILD_ENV}
        for k in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "GITHUB_TOKEN", "NEBIUS_PROJECT_ID"):
            env.pop(k, None)
        await _run([uv, "venv", "--quiet", "--python", "3.12", str(venv)], timeout=180, env=env)
        args = [uv, "pip", "install", "--quiet", "--python", str(py), "-e", spec, "pytest>=8"]
        req = root / "requirements.txt"
        if req.exists():
            args += ["-r", str(req)]
        code, out, err = await _run(args, timeout=600, env=env)
        if code != 0:
            raise SandboxError(f"project install failed: {err.strip()[-900:]}")
        return str(py), {"python": "venv", "installed": True}

    async def _venv_for(self, requirements: str) -> tuple[str, dict[str, Any]]:
        uv = shutil.which("uv")
        key = hashlib.sha256(("py312\n" + requirements.strip()).encode()).hexdigest()[:16]
        venv = _ensure(settings.workdir / "venvs") / key
        py = _venv_python(venv)
        lock = self._venv_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if py.exists() and (venv / ".polygraph-ready").exists():
                return str(py), {"python": "venv", "venv": key, "cached": True}
            if not uv:
                return sys.executable, {"python": "host", "warning": "uv not found; dependencies not isolated"}
            req_file = venv.parent / f"{key}.txt"
            req_file.write_text(requirements.rstrip() + "\npytest>=8\n", encoding="utf-8")
            await _run([uv, "venv", "--quiet", "--python", "3.12", str(venv)], timeout=180)
            code, out, err = await _run(
                [uv, "pip", "install", "--quiet", "--python", str(py), "-r", str(req_file)], timeout=600
            )
            if code != 0:
                raise SandboxError(f"dependency install failed:\n{err[-1500:]}")
            (venv / ".polygraph-ready").write_text("ok")
            return str(py), {"python": "venv", "venv": key, "cached": False}

    def _env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in _SAFE_ENV if k in os.environ}
        env.update(PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        return env

    async def run_suite(self, universe: Universe, timeout: int) -> dict[str, Any]:
        t0 = time.perf_counter()
        code, out, err = await _run(
            [str(universe.backend_ref), "-s", *PYTEST_ARGS], timeout=timeout, cwd=universe.root, env=self._env()
        )
        return parse_pytest(code, out + ("\n" + err if code not in (0, 1) else ""), time.perf_counter() - t0)

    async def run(self, universe: Universe, probes: list[dict[str, Any]], timeout: int) -> dict[str, Any]:
        fd, probe_path = tempfile.mkstemp(suffix=".json", dir=self._tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(probes, fh)
        env = self._env()
        env["POLYGRAPH_CASE_TIMEOUT"] = str(max(2, min(8, timeout // 4)))
        try:
            code, out, err = await _run(
                [str(universe.backend_ref), "-s", str(self._harness), str(universe.root), probe_path],
                timeout=timeout,
                cwd=universe.root,
                env=env,
            )
        finally:
            try:
                os.unlink(probe_path)
            except OSError:
                pass
        return parse_harness_output(out, err)

    async def close(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _run(
    cmd: list[str], timeout: int, cwd: Path | None = None, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SandboxError(f"timed out after {timeout}s: {' '.join(cmd[:2])}") from None
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
