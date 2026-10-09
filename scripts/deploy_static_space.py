"""Deploy the static build (web/dist-pages built with --base /) to a free Hugging Face Static Space.

Usage: python scripts/build_pages.py --base / && python scripts/deploy_static_space.py [space_name]
"""

import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
NAME = sys.argv[1] if len(sys.argv) > 1 else "polygraph"

README = """---
title: Polygraph
emoji: 🔬
colorFrom: red
colorTo: gray
sdk: static
app_file: index.html
pinned: true
license: apache-2.0
short_description: Checks pull request claims by running old and new code
tags:
  - nvidia-nemotron
  - nebius
  - code-review
  - agents
---

# Polygraph

Every pull request makes claims. Polygraph checks them by experiment.

This Space hosts the web app with every recorded run replaying in the browser. Source, CLI, GitHub Action and the
live backend: https://github.com/Thanatos9404/polygraph
"""


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    api = HfApi(token=env["HF_TOKEN"])
    user = api.whoami()["name"]
    repo_id = f"{user}/{NAME}"
    stage = Path(tempfile.mkdtemp(prefix="polygraph-static-"))
    shutil.copytree(ROOT / "web" / "dist-pages", stage, dirs_exist_ok=True)
    (stage / "README.md").write_text(README, encoding="utf-8")
    api.create_repo(repo_id, repo_type="space", space_sdk="static", private=False, exist_ok=True)
    api.upload_folder(folder_path=str(stage), repo_id=repo_id, repo_type="space", commit_message="Deploy static Polygraph")
    shutil.rmtree(stage, ignore_errors=True)
    print(f"https://huggingface.co/spaces/{repo_id}")
    print(f"https://{user}-{NAME}.static.hf.space")


if __name__ == "__main__":
    main()
