"""Nebius Token Factory Sandboxes executor (beta).

Each universe becomes an immutable sandbox image: python:3.12-slim plus the source tree plus its pinned
dependencies. Probes then run as disposable operations branched from that image, so the base universe,
its calibration twin, and the head universe all start from recorded, reproducible filesystem states.

Requires `pip install contree-sdk==0.3.6`, NEBIUS_API_KEY, NEBIUS_PROJECT_ID, and Sandboxes access on
the project (request it at tokenfactory.nebius.com/sandboxes/about).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..analysis import SKIP_DIRS
from ..config import settings
from . import BUILD_ENV, HARNESS_PATH, PYTEST_ARGS, SandboxError, Universe, install_spec, parse_harness_output, parse_pytest

BASE_IMAGE = os.getenv("POLYGRAPH_SANDBOX_IMAGE", "docker.io/library/python:3.12-slim")
WORK = "/work"
HARNESS = "/opt/polygraph/harness.py"
MAX_UPLOAD_FILES = 2000


class NebiusSandboxExecutor:
    name = "nebius-sandboxes"

    def __init__(self) -> None:
        if not (settings.nebius_api_key and settings.nebius_project_id):
            raise SandboxError("Token Factory Sandboxes needs NEBIUS_API_KEY and NEBIUS_PROJECT_ID in .env")
        try:
            from contree_sdk import Contree
        except ImportError as e:  # pragma: no cover - optional dependency
            raise SandboxError("install the optional extra: pip install 'polygraph-pr[sandboxes]'") from e
        os.environ.setdefault("NEBIUS_PROJECT_ID", settings.nebius_project_id)
        self.client = Contree()
        self._base = None

    async def _base_image(self):
        if self._base is None:
            self._base = await self.client.images.oci(BASE_IMAGE)
        return self._base

    async def prepare(self, label: str, root: Path, requirements: str | None) -> Universe:
        base = await self._base_image()
        files: dict[str, bytes] = {HARNESS: HARNESS_PATH.read_bytes()}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(p in SKIP_DIRS or p.startswith(".") for p in rel.split("/")[:-1]):
                continue
            files[f"{WORK}/{rel}"] = path.read_bytes()
            if len(files) > MAX_UPLOAD_FILES:
                raise SandboxError("source tree too large for a sandbox upload")
        files["/opt/polygraph/requirements.txt"] = ((requirements or "").rstrip() + "\npytest>=8\n").encode()
        setup = "pip install --quiet --disable-pip-version-check -r /opt/polygraph/requirements.txt"
        spec = install_spec(root)
        if spec:
            target = WORK + spec[len(root.as_posix()):]
            exports = " ".join(f"{k}={v}" for k, v in BUILD_ENV.items())
            setup += f" && {exports} pip install --quiet --disable-pip-version-check -e '{target}'"
        prepared = await base.run(shell=setup, files=files, cwd=WORK, disposable=False, timeout=600)
        if prepared.exit_code != 0 or prepared.uuid is None:
            raise SandboxError(f"universe {label} setup failed: {(prepared.stderr or '')[-1200:]}")
        image = await self.client.images.use(prepared.uuid, strict=True)
        return Universe(
            label=label,
            root=root,
            requirements=requirements,
            backend_ref=image,
            meta={"backend": "nebius-sandboxes", "image_uuid": str(prepared.uuid), "base": BASE_IMAGE},
        )

    async def run(self, universe: Universe, probes: list[dict[str, Any]], timeout: int) -> dict[str, Any]:
        image = universe.backend_ref
        result = await image.run(
            shell=f"PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 python -s {HARNESS} {WORK} /tmp/probes.json",
            files={"/tmp/probes.json": json.dumps(probes).encode()},
            cwd=WORK,
            disposable=True,
            timeout=timeout,
            truncate_output_at=10 * 1024 * 1024,
        )
        return parse_harness_output(result.stdout or "", result.stderr or "")

    async def run_suite(self, universe: Universe, timeout: int) -> dict[str, Any]:
        t0 = time.perf_counter()
        result = await universe.backend_ref.run(
            shell="python -s " + " ".join(PYTEST_ARGS), cwd=WORK, disposable=True, timeout=timeout
        )
        return parse_pytest(result.exit_code or 0, result.stdout or "", time.perf_counter() - t0)

    async def close(self) -> None:
        return None
