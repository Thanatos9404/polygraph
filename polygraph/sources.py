"""Where a change comes from: a public GitHub PR, two refs in a local repo, or a bundled scenario."""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tarfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .config import ROOT, settings

SCENARIOS_DIR = ROOT / "scenarios"
MAX_TARBALL = 60 * 1024 * 1024
_PR_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
_ISSUE_REF = re.compile(r"(?:(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+)?#(\d+)\b", re.I)


class SourceError(RuntimeError):
    pass


@dataclass
class Subject:
    id: str
    kind: str  # github | local | scenario
    title: str
    body: str
    repo: str
    base_ref: str
    head_ref: str
    url: str | None
    root_a: Path
    root_b: Path
    commits: list[str] = field(default_factory=list)
    linked_issues: list[dict[str, Any]] = field(default_factory=list)
    author: str | None = None
    scenario: str | None = None

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("root_a")
        d.pop("root_b")
        return d

    def pr_text(self) -> str:
        parts = [f"Title: {self.title}", "", "Description:", self.body.strip() or "(empty)"]
        if self.commits:
            parts += ["", "Commit messages:"] + [f"- {c.strip()}" for c in self.commits[:30]]
        for issue in self.linked_issues:
            parts += ["", f"Linked issue #{issue['number']}: {issue['title']}", (issue.get("body") or "")[:1500]]
        return "\n".join(parts)


def _workspace(run_id: str) -> Path:
    p = settings.workdir / "runs" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_extract(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        for m in tar.getmembers():
            if not (m.isfile() or m.isdir()):
                continue
            parts = Path(m.name).parts[1:]  # drop the codeload top-level folder
            if not parts or any(p in ("..", "") for p in parts) or Path(m.name).is_absolute():
                continue
            target = dest.joinpath(*parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            fh = tar.extractfile(m)
            if fh:
                target.write_bytes(fh.read())


def _gh_headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "polygraph-pr"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


async def from_github(url: str, run_id: str | None = None) -> Subject:
    m = _PR_URL.search(url)
    if not m:
        raise SourceError("expected a URL like https://github.com/owner/repo/pull/123")
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    run_id = run_id or uuid.uuid4().hex[:12]
    ws = _workspace(run_id)
    async with httpx.AsyncClient(timeout=60, headers=_gh_headers(), follow_redirects=True) as client:
        r = await client.get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}")
        if r.status_code == 404:
            raise SourceError("pull request not found or repository is private")
        r.raise_for_status()
        pr = r.json()
        commits_r = await client.get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/commits?per_page=50")
        commits = [c["commit"]["message"] for c in commits_r.json()] if commits_r.status_code == 200 else []
        base_full = pr["base"]["repo"]["full_name"]
        head_repo = pr["head"].get("repo") or pr["base"]["repo"]
        head_full = head_repo["full_name"]

        async def fetch(full: str, sha: str, dest: Path) -> None:
            async with client.stream("GET", f"https://codeload.github.com/{full}/tar.gz/{sha}") as resp:
                if resp.status_code != 200:
                    raise SourceError(f"could not download {full}@{sha[:7]} ({resp.status_code})")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_TARBALL:
                        raise SourceError("repository snapshot exceeds 60 MB")
            _safe_extract(bytes(buf), dest)

        await fetch(base_full, pr["base"]["sha"], ws / "a")
        await fetch(head_full, pr["head"]["sha"], ws / "b")

        issues: list[dict[str, Any]] = []
        refs = list(dict.fromkeys(int(n) for n in _ISSUE_REF.findall((pr.get("body") or "") + " " + pr["title"])))
        for n in refs[:3]:
            if n == number:
                continue
            ir = await client.get(f"https://api.github.com/repos/{owner}/{repo}/issues/{n}")
            if ir.status_code == 200:
                j = ir.json()
                issues.append({"number": n, "title": j.get("title", ""), "body": (j.get("body") or "")[:3000]})

    return Subject(
        id=run_id,
        kind="github",
        title=pr["title"],
        body=pr.get("body") or "",
        repo=base_full,
        base_ref=f"{pr['base']['ref']}@{pr['base']['sha'][:7]}",
        head_ref=f"{pr['head']['ref']}@{pr['head']['sha'][:7]}",
        url=pr["html_url"],
        root_a=ws / "a",
        root_b=ws / "b",
        commits=commits,
        linked_issues=issues,
        author=(pr.get("user") or {}).get("login"),
    )


def from_local(repo: Path, base: str, head: str, title: str | None = None, body: str | None = None,
               run_id: str | None = None) -> Subject:
    repo = repo.resolve()
    run_id = run_id or uuid.uuid4().hex[:12]
    ws = _workspace(run_id)

    def git(*args: str) -> bytes:
        res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
        if res.returncode != 0:
            raise SourceError(res.stderr.decode("utf-8", "replace").strip())
        return res.stdout

    for ref, dest in ((base, ws / "a"), (head, ws / "b")):
        if ref == "WORKTREE":
            shutil.copytree(repo, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".venv", "node_modules"))
            continue
        data = git("archive", "--format=tar", "--prefix=root/", ref)
        _safe_extract(data, dest)
    head_for_log = "HEAD" if head == "WORKTREE" else head
    log = git("log", "--format=%B%x00", f"{base}..{head_for_log}").decode("utf-8", "replace")
    commits = [c.strip() for c in log.split("\x00") if c.strip()]
    return Subject(
        id=run_id,
        kind="local",
        title=title or (commits[0].splitlines()[0] if commits else f"{base}..{head}"),
        body=body or "",
        repo=repo.name,
        base_ref=base,
        head_ref=head,
        url=None,
        root_a=ws / "a",
        root_b=ws / "b",
        commits=commits,
    )


def list_scenarios() -> list[dict[str, Any]]:
    out = []
    for d in sorted(SCENARIOS_DIR.iterdir() if SCENARIOS_DIR.exists() else []):
        meta = d / "pr.json"
        if meta.exists():
            j = json.loads(meta.read_text(encoding="utf-8"))
            out.append({"id": d.name, **{k: j.get(k) for k in ("title", "repo", "blurb", "author", "order")}})
    return sorted(out, key=lambda s: (s.get("order") or 99, s["id"]))


def from_scenario(name: str, run_id: str | None = None) -> Subject:
    d = SCENARIOS_DIR / name
    if not (d / "pr.json").exists() or not re.fullmatch(r"[\w-]+", name):
        raise SourceError(f"unknown scenario {name}")
    meta = json.loads((d / "pr.json").read_text(encoding="utf-8"))
    run_id = run_id or uuid.uuid4().hex[:12]
    ws = _workspace(run_id)
    shutil.copytree(d / "base", ws / "a", dirs_exist_ok=True)
    shutil.copytree(d / "head", ws / "b", dirs_exist_ok=True)
    return Subject(
        id=run_id,
        kind="scenario",
        title=meta["title"],
        body=meta.get("body", ""),
        repo=meta.get("repo", name),
        base_ref=meta.get("base_ref", "main"),
        head_ref=meta.get("head_ref", "pr"),
        url=meta.get("url"),
        root_a=ws / "a",
        root_b=ws / "b",
        commits=meta.get("commits", []),
        linked_issues=meta.get("linked_issues", []),
        author=meta.get("author"),
        scenario=name,
    )


def requirements_for(root: Path) -> str | None:
    """Runtime dependencies a universe needs, flattened to requirements.txt syntax."""
    req = root / "requirements.txt"
    if req.exists():
        lines = [
            ln for ln in req.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith(("#", "-e", "-r", "--"))
        ]
        return "\n".join(lines) + "\n" if lines else None
    pp = root / "pyproject.toml"
    if pp.exists():
        import tomllib

        try:
            deps = tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {}).get("dependencies", [])
        except tomllib.TOMLDecodeError:
            return None
        return "\n".join(deps) + "\n" if deps else None
    return None
