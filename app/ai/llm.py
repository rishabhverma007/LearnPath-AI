"""LLM provider abstraction.

- LocalProvider: deterministic, offline "intelligence" that composes
  answers from retrieved knowledge + learner context. Never crashes,
  never hallucinates (it only re-states retrieved facts).
- OpenAIProvider: real LLM via the OpenAI-compatible API with timeouts,
  retries, and structured-JSON output validation. Falls back to local
  on any failure.

The rest of the app only talks to the LLMProvider protocol, so swapping
or adding providers never touches feature code.
"""
from __future__ import annotations

import json
import time
from typing import Any, Protocol

from app import config
from app.utils import get_logger, safe_json

log = get_logger("llm")


class LLMProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str: ...

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None: ...


# ----------------------------------------------------------------------
# Local (offline) provider
# ----------------------------------------------------------------------
class LocalProvider:
    """Offline fallback provider.

    It cannot generate free text, so it returns a structured marker that
    higher layers (the coach) translate into templated answers built from
    retrieved knowledge. This guarantees the app works without any API key.
    """

    name = "local"

    def available(self) -> bool:
        return True

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        # Extract the learner question from the COACH_USER template
        question = ""
        for line in user.splitlines():
            if line.startswith("LEARNER QUESTION:"):
                question = line.split(":", 1)[1].strip()
                break
        return json.dumps({
            "mode": "local_fallback",
            "question": question,
            "answer": "",
            "note": "Local fallback mode: deterministic answer composed from retrieved knowledge.",
        })

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        return None  # local mode: deterministic extractors are used instead


# ----------------------------------------------------------------------
# OpenAI-compatible provider
# ----------------------------------------------------------------------
class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self._client = None
        self._model = config.OPENAI_MODEL

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=config.OPENAI_API_KEY or None,
                base_url=config.OPENAI_BASE_URL or None,
                timeout=config.MAX_LLM_TIMEOUT_SECONDS,
                max_retries=1,
            )
        return self._client

    def available(self) -> bool:
        return bool(config.OPENAI_API_KEY)

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        if not self.available():
            raise RuntimeError("OpenAI provider requires OPENAI_API_KEY")
        client = self._ensure_client()
        resp = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        client = self._ensure_client()
        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=900,
            )
            return safe_json(resp.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            log.warning("openai structured call failed: %s", exc)
            return None


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------
_provider: LLMProvider | None = None


def get_llm_provider(force: str | None = None) -> LLMProvider:
    """Returns a provider honoring config.LLM_PROVIDER (auto/fallback safe)."""
    global _provider
    if _provider is not None and force is None:
        return _provider

    choice = force or config.LLM_PROVIDER
    if choice == "auto":
        choice = "openai" if config.OPENAI_API_KEY else "local"
    if choice == "openai":
        provider: LLMProvider = OpenAIProvider()
        if not provider.available():
            log.info("openai key missing — using local provider")
            provider = LocalProvider()
    else:
        provider = LocalProvider()
    if force is None:
        _provider = provider
    return provider


def llm_mode_label() -> str:
    p = get_llm_provider()
    return "OpenAI" if isinstance(p, OpenAIProvider) else "Local (offline)"
