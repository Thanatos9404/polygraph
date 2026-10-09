"""Outside evidence for the experiment planner, gathered with Tavily.

Two questions are worth a web lookup during review: what changed inside a dependency that the PR bumps,
and what the issues or pages the PR links to actually describe. Both feed the planner so probes target
the behavior that is most likely to have moved.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from .analysis import DependencyChange
from .budget import ledger
from .config import settings

TAVILY = "https://api.tavily.com"
_URL = re.compile(r"https?://[^\s)>\]]+")


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    # Basic search costs 1 credit; basic extract costs 1 credit per 5 URLs.
    ledger.take_tavily(1 if path == "/search" else max(1, -(-len(payload.get("urls", [])) // 5)))
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(
            f"{TAVILY}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
        )
        r.raise_for_status()
        return r.json()


def _clean_version(spec: str | None) -> str:
    if not spec:
        return "unpinned"
    m = re.search(r"\d+(\.\d+)*[\w.-]*", spec)
    return m.group(0) if m else spec


async def _project_urls(package: str) -> dict[str, str]:
    """Official URLs a package publishes on PyPI (no Tavily credit spent)."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"https://pypi.org/pypi/{package}/json")
            if r.status_code != 200:
                return {}
            info = r.json().get("info", {})
            urls = {k.lower(): v for k, v in (info.get("project_urls") or {}).items() if v}
            if info.get("home_page"):
                urls.setdefault("homepage", info["home_page"])
            return urls
    except httpx.HTTPError:
        return {}


async def dependency_notes(change: DependencyChange) -> dict[str, Any]:
    """Read the dependency's own changelog (Tavily Extract) and search its own sites for breaking changes (Tavily Search)."""
    before, after = _clean_version(change.before), _clean_version(change.after)
    urls = await _project_urls(change.package)
    changelog = next(
        (v for k, v in urls.items() if any(w in k for w in ("changelog", "change log", "release", "history", "news", "changes"))),
        None,
    )
    hosts = {httpx.URL(v).host for v in urls.values() if v.startswith("http")} - {"pypi.org", ""}
    # A project's own docs site beats all of github.com as a search scope.
    domains = sorted(hosts - {"github.com"} or hosts)[:4]
    query = f"{change.package} {after} release notes breaking changes removed since {before}"
    search_payload: dict[str, Any] = {"query": query, "search_depth": "basic", "max_results": 5, "include_answer": True}
    if domains:
        search_payload["include_domains"] = domains
    try:
        data = await _post("/search", search_payload)
    except httpx.HTTPError:
        data = {}
    if not changelog:
        changelog = next(
            (r.get("url") for r in data.get("results", []) if re.search(r"change|release|history|news", r.get("url", ""), re.I)),
            None,
        )
    results: list[Any] = [data]
    if changelog:
        results.append(await asyncio.gather(_post("/extract", {"urls": [changelog], "extract_depth": "basic"}), return_exceptions=True))
        results[1] = results[1][0]
    sources = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("content") or "")[:700]}
        for r in data.get("results", []) if r.get("url") != changelog
    ]
    excerpt = ""
    if changelog and len(results) > 1 and not isinstance(results[1], Exception):
        pages = results[1].get("results", [])
        excerpt = _window(pages[0].get("raw_content", ""), before, after) if pages else ""
    return {
        "kind": "dependency",
        "package": change.package,
        "before": before,
        "after": after,
        "query": query,
        "changelog": changelog,
        "changelog_excerpt": excerpt,
        "answer": data.get("answer") or "",
        "sources": ([{"title": "Official changelog", "url": changelog, "snippet": excerpt[:700]}] if changelog else []) + sources,
    }


def _window(text: str, before: str, after: str, limit: int = 6000) -> str:
    """The slice of a changelog between the new version's entry and the old one's."""
    if not text:
        return ""
    lo = text.find(after)
    hi = text.find(before, lo + 1 if lo >= 0 else 0)
    if lo >= 0 and hi > lo:
        return text[lo:hi][:limit]
    return text[:limit]


async def linked_pages(text: str, limit: int = 3) -> dict[str, Any] | None:
    urls = []
    for u in _URL.findall(text or ""):
        u = u.rstrip(".,;")
        if "github.com" in u and ("/pull/" in u or "/compare/" in u):
            continue
        if u not in urls:
            urls.append(u)
    if not urls:
        return None
    data = await _post("/extract", {"urls": urls[:limit], "extract_depth": "basic"})
    pages = [
        {"url": r.get("url", ""), "excerpt": (r.get("raw_content") or "")[:2500]} for r in data.get("results", [])
    ]
    return {"kind": "links", "pages": pages}


def render_notes(notes: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for n in notes:
        if n["kind"] == "dependency":
            out.append(f"### {n['package']} {n['before']} -> {n['after']}")
            if n.get("changelog_excerpt"):
                out.append(f"Official changelog ({n['changelog']}), entries between the two versions:\n{n['changelog_excerpt'][:4000]}")
            if n.get("answer"):
                out.append(n["answer"])
            for s in n["sources"][:4]:
                out.append(f"- {s['title']} ({s['url']}): {s['snippet'][:400]}")
        elif n["kind"] == "links":
            for p in n["pages"]:
                out.append(f"### Linked page {p['url']}\n{p['excerpt'][:1500]}")
    return "\n".join(out)
