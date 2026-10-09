"""Static analysis of two source trees: what changed, what it touches, and what can be probed."""

from __future__ import annotations

import ast
import difflib
import hashlib
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build", "dist", ".tox", ".mypy_cache",
    ".pytest_cache", "site-packages", ".eggs", "docs", "examples", "benchmarks",
}
MAX_FILE_BYTES = 400_000

# Distribution names whose import name differs.
IMPORT_NAMES = {
    "python-dateutil": "dateutil", "pyyaml": "yaml", "beautifulsoup4": "bs4", "pillow": "PIL",
    "scikit-learn": "sklearn", "attrs": "attr", "typing-extensions": "typing_extensions",
    "protobuf": "google", "msgpack-python": "msgpack", "pyjwt": "jwt", "python-slugify": "slugify",
}


@dataclass
class Symbol:
    qualname: str  # e.g. "pkg.module:Class.method"
    module: str
    name: str
    kind: str  # function | method | class
    signature: str
    source: str
    lineno: int
    public: bool
    calls: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    imported_names: dict[str, str] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return hashlib.sha1(_normalize(self.source).encode()).hexdigest()


@dataclass
class Target:
    qualname: str
    module: str
    name: str
    kind: str
    status: str  # changed | added | removed | caller | dependency
    reason: str
    signature_a: str | None
    signature_b: str | None
    source_a: str | None
    source_b: str | None
    public: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DependencyChange:
    package: str
    before: str | None
    after: str | None
    file: str


@dataclass
class TreeDiff:
    files_changed: list[str]
    files_added: list[str]
    files_removed: list[str]
    unified_diff: str
    stats: dict[str, int]
    targets: list[Target]
    dependency_changes: list[DependencyChange]
    tests_changed: list[str]
    modules_a: dict[str, str]
    modules_b: dict[str, str]

    def summary(self) -> dict:
        return {
            "files_changed": self.files_changed,
            "files_added": self.files_added,
            "files_removed": self.files_removed,
            "stats": self.stats,
            "dependency_changes": [asdict(d) for d in self.dependency_changes],
            "tests_changed": self.tests_changed,
            "targets": [
                {k: v for k, v in t.to_dict().items() if k not in ("source_a", "source_b")} for t in self.targets
            ],
        }


def _normalize(src: str) -> str:
    return "\n".join(line.rstrip() for line in src.strip().splitlines())


def is_test_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    name = parts[-1]
    return (
        "tests" in parts[:-1]
        or "test" in parts[:-1]
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def iter_files(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.split("/")[:-1]):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        if path.suffix in {".py", ".txt", ".toml", ".cfg", ".md", ".rst", ".json", ".yaml", ".yml", ".ini", ""}:
            try:
                out[rel] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return out


def module_name(rel: str) -> str:
    rel = rel[:-3] if rel.endswith(".py") else rel
    parts = rel.split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class _Collector(ast.NodeVisitor):
    def __init__(self, module: str, source: str) -> None:
        self.module = module
        self.source = source
        self.stack: list[str] = []
        self.symbols: list[Symbol] = []
        self.module_imports: set[str] = set()
        self.imported_names: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            top = a.name.split(".")[0]
            self.module_imports.add(top)
            self.imported_names[a.asname or top] = top

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            top = node.module.split(".")[0]
            self.module_imports.add(top)
            for a in node.names:
                self.imported_names[a.asname or a.name] = top

    def _add(self, node: ast.AST, kind: str) -> None:
        name = node.name  # type: ignore[attr-defined]
        qual = ".".join([*self.stack, name])
        src = ast.get_source_segment(self.source, node) or ""
        decorators = "".join(
            "@" + (ast.get_source_segment(self.source, d) or "") + "\n" for d in getattr(node, "decorator_list", [])
        )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = f"def {name}({ast.unparse(node.args)})"
            if node.returns is not None:
                sig += f" -> {ast.unparse(node.returns)}"
        else:
            bases = ", ".join(ast.unparse(b) for b in node.bases)  # type: ignore[attr-defined]
            sig = f"class {name}({bases})" if bases else f"class {name}"
        calls: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Name):
                    calls.add(f.id)
                elif isinstance(f, ast.Attribute):
                    calls.add(f.attr)
            elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                calls.add(sub.value.id)
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                calls.add(sub.id)  # references such as key=parse count as uses
        public = not any(p.startswith("_") and not (p.startswith("__") and p.endswith("__")) for p in [*self.stack, name])
        public = public and not any(seg.startswith("_") for seg in self.module.split(".") if seg)
        self.symbols.append(
            Symbol(
                qualname=f"{self.module}:{qual}",
                module=self.module,
                name=qual,
                kind=kind,
                signature=sig,
                source=decorators + src,
                lineno=node.lineno,  # type: ignore[attr-defined]
                public=public,
                calls=calls,
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node, "method" if self.stack else "function")
        # Nested functions are part of their parent's behavior; do not descend.

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node, "class")
        self.stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self.stack.pop()


def collect_symbols(files: dict[str, str]) -> tuple[dict[str, Symbol], dict[str, set[str]]]:
    symbols: dict[str, Symbol] = {}
    imports: dict[str, set[str]] = {}
    for rel, text in files.items():
        if not rel.endswith(".py") or is_test_path(rel) or rel in {"setup.py", "noxfile.py", "conftest.py"}:
            continue
        mod = module_name(rel)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        col = _Collector(mod, text)
        col.visit(tree)
        imports[mod] = col.module_imports
        for s in col.symbols:
            s.imports = col.module_imports
            s.imported_names = col.imported_names
            symbols[s.qualname] = s
    return symbols, imports


_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*?)\s*(#.*)?$")


def _parse_requirements(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = _REQ_LINE.match(line)
        if m:
            out[m.group(1).lower().replace("_", "-")] = (m.group(3) or "").strip()
    return out


def _parse_pyproject(text: str) -> dict[str, str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    deps = data.get("project", {}).get("dependencies", []) or []
    return _parse_requirements("\n".join(deps))


def dependency_changes(a: dict[str, str], b: dict[str, str]) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for rel in sorted(set(a) | set(b)):
        name = rel.split("/")[-1]
        if re.fullmatch(r"requirements[\w.-]*\.txt", name):
            parse = _parse_requirements
        elif name == "pyproject.toml" and "/" not in rel:
            parse = _parse_pyproject
        else:
            continue
        da, db = parse(a.get(rel, "")), parse(b.get(rel, ""))
        for pkg in sorted(set(da) | set(db)):
            if da.get(pkg) != db.get(pkg):
                changes.append(DependencyChange(pkg, da.get(pkg), db.get(pkg), rel))
    return changes


def unified(a: dict[str, str], b: dict[str, str]) -> tuple[str, dict[str, int], list[str], list[str], list[str]]:
    chunks: list[str] = []
    added = removed = 0
    changed, new, gone = [], [], []
    for rel in sorted(set(a) | set(b)):
        ta, tb = a.get(rel), b.get(rel)
        if ta == tb:
            continue
        if ta is None:
            new.append(rel)
        elif tb is None:
            gone.append(rel)
        else:
            changed.append(rel)
        lines = list(
            difflib.unified_diff(
                (ta or "").splitlines(keepends=True),
                (tb or "").splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                n=3,
            )
        )
        for ln in lines:
            if ln.startswith("+") and not ln.startswith("+++"):
                added += 1
            elif ln.startswith("-") and not ln.startswith("---"):
                removed += 1
        chunks.append("".join(ln if ln.endswith("\n") else ln + "\n" for ln in lines))
    return "".join(chunks), {"additions": added, "deletions": removed}, changed, new, gone


def diff_trees(root_a: Path, root_b: Path, max_targets: int = 12) -> TreeDiff:
    fa, fb = iter_files(root_a), iter_files(root_b)
    udiff, stats, changed, new, gone = unified(fa, fb)
    sa, imports_a = collect_symbols(fa)
    sb, imports_b = collect_symbols(fb)
    deps = dependency_changes(fa, fb)

    targets: dict[str, Target] = {}

    def add(q: str, status: str, reason: str) -> None:
        if q in targets:
            return
        a, b = sa.get(q), sb.get(q)
        s = b or a
        assert s is not None
        targets[q] = Target(
            qualname=q,
            module=s.module,
            name=s.name,
            kind=s.kind,
            status=status,
            reason=reason,
            signature_a=a.signature if a else None,
            signature_b=b.signature if b else None,
            source_a=a.source if a else None,
            source_b=b.source if b else None,
            public=s.public,
        )

    changed_syms: list[str] = []
    for q in sorted(set(sa) | set(sb)):
        a, b = sa.get(q), sb.get(q)
        if a and b and a.kind != "class" and a.digest != b.digest:
            changed_syms.append(q)
            add(q, "changed", "body changed")
        elif b and not a and b.kind != "class":
            add(q, "added", "new in head")
        elif a and not b and a.kind != "class":
            add(q, "removed", "deleted in head")

    # Public callers of changed private helpers inherit the change.
    changed_names = {sb[q].name.split(".")[-1] if q in sb else sa[q].name.split(".")[-1] for q in changed_syms}
    frontier = set(changed_names)
    for depth in range(3):
        nxt: set[str] = set()
        for q, s in sb.items():
            if s.kind == "class" or q in targets:
                continue
            if s.calls & frontier and q in sa:
                add(q, "caller", f"calls {', '.join(sorted(s.calls & frontier))}")
                nxt.add(s.name.split(".")[-1])
        frontier = nxt
        if not frontier:
            break

    # Code that leans on a bumped dependency is exposed to that dependency's behavior change.
    bumped: set[str] = set()
    for d in deps:
        name = d.package.lower()
        bumped |= {name, name.replace("-", "_"), IMPORT_NAMES.get(name, name).lower()}
    if bumped:
        for q, s in sb.items():
            if s.kind == "class" or q in targets or q not in sa:
                continue
            used = {s.imported_names[c] for c in s.calls if c in s.imported_names and s.imported_names[c].lower() in bumped}
            if used:
                add(q, "dependency", f"uses {', '.join(sorted(used))}")

    ranked = sorted(
        targets.values(),
        key=lambda t: (
            {"changed": 0, "dependency": 1, "added": 2, "caller": 3, "removed": 4}[t.status],
            not t.public,
            t.qualname,
        ),
    )
    # Keep private helpers only when no public route reaches them: probing the public entry point
    # exercises the helper the way real callers do, and its findings are ones a user can hit.
    def reached(t: Target) -> bool:
        short = t.name.split(".")[-1]
        return any(
            o.public and o.qualname in sb and short in sb[o.qualname].calls for o in ranked if o is not t
        )

    public_first = [t for t in ranked if t.public] + [t for t in ranked if not t.public and not reached(t)]
    selected = public_first[:max_targets]

    mods_a = {module_name(r): t for r, t in fa.items() if r.endswith(".py") and not is_test_path(r)}
    mods_b = {module_name(r): t for r, t in fb.items() if r.endswith(".py") and not is_test_path(r)}
    return TreeDiff(
        files_changed=changed,
        files_added=new,
        files_removed=gone,
        unified_diff=udiff,
        stats=stats,
        targets=selected,
        dependency_changes=deps,
        tests_changed=[r for r in changed + new if is_test_path(r)],
        modules_a=mods_a,
        modules_b=mods_b,
    )
