"""Build the static GitHub Pages site: the web app plus every recorded run as JSON, replayed in the browser.

Usage: python scripts/build_pages.py [--base /polygraph/] [--api https://live-backend.example]   -> web/dist-pages
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polygraph.sources import list_scenarios  # noqa: E402
from polygraph.store import RECORDED_DIR, recorded_index  # noqa: E402

WEB = ROOT / "web"
OUT = WEB / "dist-pages"


def main() -> None:
    api = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else ""
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "/polygraph/"
    env = {**os.environ, "VITE_STATIC": "1", "VITE_API_BASE": api}
    npx = shutil.which("npx") or "npx"
    subprocess.run([npx, "vite", "build", f"--base={base}", "--outDir", "dist-pages", "--emptyOutDir"], cwd=WEB, env=env, check=True, shell=os.name == "nt")

    data = OUT / "data"
    (data / "runs").mkdir(parents=True, exist_ok=True)
    recorded = recorded_index()
    by_scenario = {r.get("scenario"): r for r in recorded if r.get("scenario")}
    scenarios = [{**s, "recorded": by_scenario.get(s["id"])} for s in list_scenarios()]
    (data / "scenarios.json").write_text(json.dumps(scenarios), encoding="utf-8")
    (data / "recorded.json").write_text(json.dumps(recorded), encoding="utf-8")
    for f in RECORDED_DIR.glob("*.json"):
        shutil.copyfile(f, data / "runs" / f.name)

    shutil.copyfile(OUT / "index.html", OUT / "404.html")  # deep links such as /polygraph/run/<id>
    (OUT / ".nojekyll").write_text("")
    print(f"built {OUT} with {len(recorded)} recorded runs")


if __name__ == "__main__":
    main()
