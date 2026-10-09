"""Runtime configuration and the Nemotron model roster."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class ModelSpec:
    """One model on Nebius Token Factory and the job Polygraph gives it."""

    id: str
    label: str
    role: str
    input_price: float  # USD per million input tokens
    output_price: float  # USD per million output tokens
    thinking: bool = False

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.input_price + completion_tokens * self.output_price) / 1_000_000


# Each stage gets the smallest Nemotron that does the job well.
# Prices come from the public Token Factory catalog (tokenfactory.nebius.com/api/public/models_info).
ULTRA = ModelSpec(
    id=os.getenv("POLYGRAPH_MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
    label="Nemotron 3 Ultra",
    role="Reads the PR and the code, writes the claim ledger and the experiment plan, delivers the final verdict.",
    input_price=1.0,
    output_price=3.0,
    thinking=True,
)
SUPER = ModelSpec(
    id=os.getenv("POLYGRAPH_MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    label="Nemotron 3 Super",
    role="Explains each cluster of diverging behavior in plain language and rates its severity.",
    input_price=0.3,
    output_price=0.9,
)
LIGHTNING = ModelSpec(
    id=os.getenv("POLYGRAPH_MODEL_LIGHTNING", "nvidia/Nemotron-3_5-Lightning"),
    label="Nemotron 3.5 Lightning",
    role="Writes executable probes in parallel, one experiment per target.",
    input_price=0.06,
    output_price=0.24,
)
NANO = ModelSpec(
    id=os.getenv("POLYGRAPH_MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    label="Nemotron 3 Nano",
    role="Repairs probes that fail to run before they reach the comparison stage.",
    input_price=0.06,
    output_price=0.24,
)

ROSTER: dict[str, ModelSpec] = {"ultra": ULTRA, "super": SUPER, "lightning": LIGHTNING, "nano": NANO}

# If a tier is unavailable on the account, fall back down the list instead of failing the run.
FALLBACKS: dict[str, list[str]] = {
    "ultra": ["super", "lightning"],
    "super": ["ultra", "lightning"],
    "lightning": ["nano", "super"],
    "nano": ["lightning", "super"],
}


@dataclass
class Settings:
    nebius_api_key: str = field(default_factory=lambda: os.getenv("NEBIUS_API_KEY", "").strip())
    nebius_base_url: str = field(
        default_factory=lambda: os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    )
    nebius_project_id: str = field(default_factory=lambda: os.getenv("NEBIUS_PROJECT_ID", "").strip())
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", "").strip())
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", "").strip())
    executor: str = field(default_factory=lambda: os.getenv("POLYGRAPH_EXECUTOR", "local"))
    llm_concurrency: int = field(default_factory=lambda: int(os.getenv("POLYGRAPH_LLM_CONCURRENCY", "6")))
    exec_concurrency: int = field(default_factory=lambda: int(os.getenv("POLYGRAPH_EXEC_CONCURRENCY", "4")))
    probe_timeout_s: int = field(default_factory=lambda: int(os.getenv("POLYGRAPH_PROBE_TIMEOUT", "20")))
    max_targets: int = field(default_factory=lambda: int(os.getenv("POLYGRAPH_MAX_TARGETS", "10")))
    max_rounds: int = field(default_factory=lambda: int(os.getenv("POLYGRAPH_MAX_ROUNDS", "2")))
    workdir: Path = field(default_factory=lambda: Path(os.getenv("POLYGRAPH_WORKDIR", str(ROOT / ".polygraph"))))
    allow_remote_repos: bool = field(
        default_factory=lambda: os.getenv("POLYGRAPH_ALLOW_REMOTE", "1").lower() in {"1", "true", "yes"}
    )

    @property
    def has_llm(self) -> bool:
        return bool(self.nebius_api_key)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)


settings = Settings()
