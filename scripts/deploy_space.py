"""Deploy the committed tree to a Hugging Face Docker Space and set its secrets.

Reads HF_TOKEN, NEBIUS_API_KEY, TAVILY_API_KEY and POLYGRAPH_ACCESS_CODE from .env. Only files tracked by git
are uploaded, so .env and local run data never leave the machine.
Usage: python scripts/deploy_space.py [space_name]
"""

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
NAME = sys.argv[1] if len(sys.argv) > 1 else "polygraph"

FRONT_MATTER = """---
title: Polygraph
emoji: 🔬
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: Checks pull request claims by running old and new code
tags:
  - nvidia-nemotron
  - nebius
  - code-review
  - agents
---

"""


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    api = HfApi(token=env["HF_TOKEN"])
    user = api.whoami()["name"]
    repo_id = f"{user}/{NAME}"

    stage = Path(tempfile.mkdtemp(prefix="polygraph-space-"))
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(stage, filter="data")
    readme = stage / "README.md"
    readme.write_text(FRONT_MATTER + readme.read_text(encoding="utf-8"), encoding="utf-8")

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "POLYGRAPH_ACCESS_CODE"):
        if env.get(key):
            api.add_space_secret(repo_id, key, env[key])
    api.add_space_variable(repo_id, "POLYGRAPH_ALLOW_REMOTE", "1")
    api.upload_folder(folder_path=str(stage), repo_id=repo_id, repo_type="space", commit_message="Deploy Polygraph")
    shutil.rmtree(stage, ignore_errors=True)
    print(f"https://huggingface.co/spaces/{repo_id}")
    print(f"https://{user}-{NAME}.hf.space")


if __name__ == "__main__":
    main()
