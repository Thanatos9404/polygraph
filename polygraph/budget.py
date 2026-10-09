"""Hard spending limits for Token Factory and Tavily.

Every model call reserves its worst-case cost (prompt estimate plus max_tokens of output) before it is
sent, and settles to the metered cost afterwards. A call that could push spending past any cap is refused
before it leaves the process, so parallel calls cannot overshoot. Caps:

- lifetime: total spend this deployment may ever make (persisted to disk)
- daily: spend per UTC day
- per run: spend for a single analysis
- Tavily credits per day

The ledger lives in POLYGRAPH_WORKDIR/budget.json. On hosts with ephemeral disks, set
POLYGRAPH_BUDGET_FILE to a persistent path, or keep the daily cap low enough that a restart cannot hurt.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import settings


class BudgetExceeded(RuntimeError):
    pass


def _f(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


@dataclass
class Caps:
    lifetime_usd: float = _f("POLYGRAPH_BUDGET_USD", "20")
    daily_usd: float = _f("POLYGRAPH_DAILY_BUDGET_USD", "2")
    run_usd: float = _f("POLYGRAPH_RUN_BUDGET_USD", "0.35")
    tavily_daily_credits: int = int(_f("POLYGRAPH_TAVILY_DAILY_CREDITS", "25"))


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class Ledger:
    def __init__(self, path: Path | None = None, caps: Caps | None = None) -> None:
        self.path = path or Path(os.getenv("POLYGRAPH_BUDGET_FILE", str(settings.workdir / "budget.json")))
        self.caps = caps or Caps()
        self._lock = threading.Lock()
        self._reserved = 0.0
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"lifetime_usd": 0.0, "days": {}, "tavily": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def _day(self) -> float:
        return float(self._data["days"].get(_today(), 0.0))

    def _refresh(self) -> None:
        # Several processes (CLI, server, Action) may share one ledger file: always build on the latest totals.
        self._data = self._load()

    def remaining(self) -> float:
        with self._lock:
            self._refresh()
            return max(
                0.0,
                min(
                    self.caps.lifetime_usd - self._data["lifetime_usd"] - self._reserved,
                    self.caps.daily_usd - self._day() - self._reserved,
                ),
            )

    def check_can_start(self, min_usd: float = 0.05) -> None:
        if self.remaining() < min_usd:
            raise BudgetExceeded(
                "Spending cap reached: live analyses are paused so no paid usage can occur. "
                "Recorded runs remain available."
            )

    def reserve(self, usd: float, run_spent: float) -> None:
        with self._lock:
            self._refresh()
            if run_spent + usd > self.caps.run_usd:
                raise BudgetExceeded(f"per-run cap of ${self.caps.run_usd:.2f} reached")
            if self._data["lifetime_usd"] + self._reserved + usd > self.caps.lifetime_usd:
                raise BudgetExceeded("lifetime spending cap reached")
            if self._day() + self._reserved + usd > self.caps.daily_usd:
                raise BudgetExceeded("daily spending cap reached")
            self._reserved += usd

    def settle(self, reserved: float, actual: float) -> None:
        with self._lock:
            self._refresh()
            self._reserved = max(0.0, self._reserved - reserved)
            self._data["lifetime_usd"] = round(self._data["lifetime_usd"] + actual, 6)
            day = _today()
            self._data["days"][day] = round(self._data["days"].get(day, 0.0) + actual, 6)
            self._save()

    def take_tavily(self, credits: int) -> None:
        with self._lock:
            self._refresh()
            day = _today()
            used = int(self._data.setdefault("tavily", {}).get(day, 0))
            if used + credits > self.caps.tavily_daily_credits:
                raise BudgetExceeded("daily Tavily credit cap reached")
            self._data["tavily"][day] = used + credits
            self._save()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh()
            return {
                "lifetime_spent": round(self._data["lifetime_usd"], 4),
                "lifetime_cap": self.caps.lifetime_usd,
                "today_spent": round(self._day(), 4),
                "daily_cap": self.caps.daily_usd,
                "run_cap": self.caps.run_usd,
                "tavily_today": int(self._data.get("tavily", {}).get(_today(), 0)),
                "tavily_daily_cap": self.caps.tavily_daily_credits,
            }


ledger = Ledger()
