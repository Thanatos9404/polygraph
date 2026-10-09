"""Nebius Token Factory client with tiered Nemotron routing, JSON parsing, and cost metering."""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from .budget import BudgetExceeded, ledger
from .config import FALLBACKS, ROSTER, ModelSpec, settings
from .events import EventBus


class LLMError(RuntimeError):
    pass


@dataclass
class ModelUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost": round(self.cost, 6),
            "seconds": round(self.seconds, 2),
        }


@dataclass
class Meter:
    by_model: dict[str, ModelUsage] = field(default_factory=dict)

    def add(self, spec: ModelSpec, prompt: int, completion: int, seconds: float) -> ModelUsage:
        u = self.by_model.setdefault(spec.id, ModelUsage())
        u.calls += 1
        u.prompt_tokens += prompt
        u.completion_tokens += completion
        u.cost += spec.cost(prompt, completion)
        u.seconds += seconds
        return u

    @property
    def total_cost(self) -> float:
        return sum(u.cost for u in self.by_model.values())

    @property
    def total_tokens(self) -> int:
        return sum(u.prompt_tokens + u.completion_tokens for u in self.by_model.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost": round(self.total_cost, 6),
            "total_tokens": self.total_tokens,
            "models": {k: v.to_dict() for k, v in self.by_model.items()},
        }


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_EM = re.compile(r"\s*[\u2014\u2015]\s*")
_EN_NUM = re.compile(r"(?<=\d)\u2013(?=\d)")


def clean_text(value: Any) -> Any:
    """House style for anything a model writes that users will read: no em or en dashes."""
    if isinstance(value, str):
        value = _EN_NUM.sub("-", value)
        value = _EM.sub(", ", value)
        value = re.sub(r"\s+\u2013\s+", ", ", value).replace("\u2013", "-")
        return value.replace(" ,", ",").replace(",,", ",")
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_text(v) for k, v in value.items()}
    return value


def strip_reasoning(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    # Some deployments emit only a closing tag when the opening one is part of the template.
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str) -> Any:
    """Pull the first well-formed JSON object or array out of a model reply."""
    text = strip_reasoning(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    candidates.append(text)
    for cand in candidates:
        cand = cand.strip()
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            while start != -1:
                depth, in_str, esc = 0, False, False
                for i in range(start, len(cand)):
                    ch = cand[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == opener:
                        depth += 1
                    elif ch == closer:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(cand[start : i + 1])
                            except json.JSONDecodeError:
                                break
                start = cand.find(opener, start + 1)
    raise LLMError("model reply did not contain valid JSON")


_CODE_START = re.compile(r"^(import |from |def |class |CASES|#|@|[A-Za-z_]\w* = )")


def extract_code(text: str) -> str:
    text = strip_reasoning(text)
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    # Unclosed fence (reply cut off) or no fence at all: drop prose before the first line of code.
    text = re.sub(r"^.*?```(?:python|py)?\s*\n", "", text, count=1, flags=re.S)
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        if _CODE_START.match(line):
            return "\n".join(lines[i:]).strip() + "\n"
    return text.strip() + "\n"


class TokenFactory:
    """Thin async wrapper over the OpenAI-compatible Token Factory API."""

    def __init__(self, bus: EventBus | None = None, meter: Meter | None = None) -> None:
        if not settings.has_llm:
            raise LLMError("NEBIUS_API_KEY is not set. Add it to .env to run live analyses.")
        self.client = AsyncOpenAI(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url,
            timeout=300,
            max_retries=0,
        )
        self.bus = bus
        self.meter = meter or Meter()
        self._sem = asyncio.Semaphore(settings.llm_concurrency)
        self._disabled: set[str] = set()
        self._no_template_kwargs: set[str] = set()
        self._run_reserved = 0.0

    def _chain(self, tier: str) -> list[ModelSpec]:
        order = [tier, *FALLBACKS.get(tier, [])]
        return [ROSTER[t] for t in order if ROSTER[t].id not in self._disabled]

    async def chat(
        self,
        tier: str,
        messages: list[dict[str, str]],
        *,
        purpose: str,
        max_tokens: int = 4096,
        temperature: float = 0.6,
        json_mode: bool = False,
        thinking: bool | None = None,
    ) -> str:
        last_err: Exception | None = None
        for spec in self._chain(tier):
            try:
                return await self._call(spec, messages, purpose, max_tokens, temperature, json_mode, thinking)
            except APIStatusError as e:
                last_err = e
                # 404 or 400 on model name means this tier is not served for this account.
                if e.status_code in (400, 403, 404) and "model" in str(e).lower():
                    self._disabled.add(spec.id)
                    continue
                if e.status_code >= 500:
                    continue
                raise LLMError(f"{spec.label}: {e}") from e
            except (APIConnectionError, asyncio.TimeoutError) as e:
                last_err = e
                continue
        raise LLMError(f"all models failed for {purpose}: {last_err}")

    async def _call(
        self,
        spec: ModelSpec,
        messages: list[dict[str, str]],
        purpose: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
        thinking: bool | None,
    ) -> str:
        use_thinking = spec.thinking if thinking is None else thinking
        extra: dict[str, Any] = {}
        if spec.id not in self._no_template_kwargs:
            extra["chat_template_kwargs"] = {"enable_thinking": use_thinking}
        kwargs: dict[str, Any] = dict(
            model=spec.id,
            messages=messages,
            max_tokens=max_tokens + (4000 if use_thinking else 0),
            temperature=temperature,
            top_p=0.95,
        )
        if json_mode and not use_thinking:
            kwargs["response_format"] = {"type": "json_object"}
        prompt_chars = sum(len(m["content"]) for m in messages)
        est_prompt = int(prompt_chars / 3) + 50
        reserved = spec.cost(est_prompt, kwargs["max_tokens"])
        ledger.reserve(reserved, self.meter.total_cost + self._run_reserved)
        self._run_reserved += reserved
        settled = False
        try:
            resp = await self._send(spec, kwargs, extra)
            elapsed = resp._polygraph_elapsed  # type: ignore[attr-defined]
            usage = resp.usage
            pt = usage.prompt_tokens if usage else est_prompt
            ct = usage.completion_tokens if usage else kwargs["max_tokens"]
            ledger.settle(reserved, spec.cost(pt, ct))
            settled = True
        finally:
            self._run_reserved -= reserved
            if not settled:
                # Unknown outcome: charge the prompt estimate so the ledger never under-counts.
                ledger.settle(reserved, spec.cost(est_prompt, 0))
        return await self._finish(spec, resp, pt, ct, elapsed, purpose)

    async def _send(self, spec: ModelSpec, kwargs: dict[str, Any], extra: dict[str, Any]):
        delay = 2.0
        async with self._sem:
            for attempt in range(5):
                t0 = time.perf_counter()
                try:
                    resp = await self.client.chat.completions.create(**kwargs, extra_body=extra or None)
                    break
                except RateLimitError:
                    await asyncio.sleep(delay)
                    delay *= 2
                except APIStatusError as e:
                    msg = str(e).lower()
                    if e.status_code == 400 and "chat_template_kwargs" in msg and extra:
                        self._no_template_kwargs.add(spec.id)
                        extra = {}
                        continue
                    if e.status_code == 400 and "response_format" in kwargs:
                        kwargs.pop("response_format")
                        continue
                    if e.status_code >= 500 and attempt < 2:
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    raise
            else:
                raise LLMError(f"{spec.label}: rate limited after retries")
        resp._polygraph_elapsed = time.perf_counter() - t0  # type: ignore[attr-defined]
        return resp

    async def _finish(self, spec: ModelSpec, resp, pt: int, ct: int, elapsed: float, purpose: str) -> str:
        self.meter.add(spec, pt, ct, elapsed)
        if self.bus:
            await self.bus.emit(
                "model_call",
                model=spec.id,
                label=spec.label,
                purpose=purpose,
                prompt_tokens=pt,
                completion_tokens=ct,
                seconds=round(elapsed, 2),
                cost=round(spec.cost(pt, ct), 6),
                total_cost=round(self.meter.total_cost, 6),
            )
        msg = resp.choices[0].message
        content = msg.content or ""
        if not content.strip():
            # Reasoning deployments sometimes put everything in reasoning_content when the budget runs out.
            content = getattr(msg, "reasoning_content", None) or ""
        return content

    async def json(
        self,
        tier: str,
        system: str,
        user: str,
        *,
        purpose: str,
        max_tokens: int = 4096,
        temperature: float = 0.4,
        thinking: bool | None = None,
        require: str | None = None,
    ) -> Any:
        """JSON from a model. With `require`, a reply missing that key (or holding it empty) is retried once
        with reasoning off, which is what happens when a reasoning budget runs out before the answer."""
        result = await self._json_once(tier, system, user, purpose, max_tokens, temperature, thinking)
        if require and (not isinstance(result, dict) or not result.get(require)):
            result = await self._json_once(tier, system, user, purpose + " (direct)", max_tokens, temperature, False)
        return result

    async def _json_once(self, tier, system, user, purpose, max_tokens, temperature, thinking) -> Any:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last: Exception | None = None
        for _ in range(2):
            text = await self.chat(
                tier,
                messages,
                purpose=purpose,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=True,
                thinking=thinking,
            )
            try:
                return clean_text(extract_json(text))
            except LLMError as e:
                last = e
                messages = messages + [
                    {"role": "assistant", "content": text[-4000:]},
                    {"role": "user", "content": "That was not valid JSON. Reply with only the JSON object."},
                ]
        raise LLMError(f"{purpose}: {last}")
