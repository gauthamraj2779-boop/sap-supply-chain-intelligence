"""Multi-provider LLM abstraction.

Four of the five providers speak the OpenAI wire format and differ only in
base_url and auth, so they share one code path; Gemini has its own SDK.

Contract with the rest of the system: **this module never raises.** Every
method returns ``None`` on any failure -- missing key, bad model, rate limit,
network outage. Callers treat prose as a garnish they can do without, which is
what lets the backend serve complete financial results with no LLM at all.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Providers that are OpenAI-wire-compatible: (base_url, key_attr, model_attr)
_OPENAI_COMPATIBLE = {
    "openai": (None, "openai_api_key", "openai_model"),
    "deepseek": ("https://api.deepseek.com", "deepseek_api_key", "deepseek_model"),
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key", "groq_model"),
}


@dataclass
class LLMStatus:
    provider: str
    model: str | None
    available: bool
    reason: str


@dataclass
class ToolCall:
    """One tool the model asked for, with its arguments already parsed.

    ``arguments`` is ``{}`` when the model emitted malformed JSON; the caller
    decides what to do about that rather than the client raising.
    """

    id: str
    name: str
    arguments: dict
    raw_arguments: str


@dataclass
class ToolTurn:
    """One assistant turn of a tool-calling conversation.

    ``assistant_message`` is the exact dict to append to the running message
    list, so the caller never has to reconstruct the wire format.
    """

    content: str | None
    tool_calls: list[ToolCall]
    assistant_message: dict
    finish_reason: str | None


class LLMClient:
    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()
        self._client: Any = None
        self._kind: str | None = None
        self._model: str | None = None
        self._reason = "not initialised"
        self._init()

    # ------------------------------------------------------------------
    def _init(self) -> None:
        s = self.settings
        provider = s.llm_provider

        if provider == "none":
            self._reason = "LLM_PROVIDER=none; running deterministic-only by configuration"
            return

        try:
            if provider in _OPENAI_COMPATIBLE:
                base_url, key_attr, model_attr = _OPENAI_COMPATIBLE[provider]
                key = getattr(s, key_attr)
                if not key:
                    self._reason = f"{key_attr.upper()} is not set"
                    return
                from openai import OpenAI

                self._client = OpenAI(api_key=key, base_url=base_url, timeout=30.0, max_retries=1)
                self._kind, self._model = "openai", getattr(s, model_attr)

            elif provider == "azure":
                if not (s.azure_key and s.azure_openai_endpoint
                        and s.azure_openai_deployment):
                    self._reason = ("AZURE_OPENAI_API_KEY / _ENDPOINT / _DEPLOYMENT "
                                    "are not all set")
                    return

                if s.azure_is_v1_endpoint:
                    # Azure AI Foundry v1: plain OpenAI protocol, bearer auth,
                    # model name is the deployment name.
                    from openai import OpenAI

                    self._client = OpenAI(
                        api_key=s.azure_key,
                        base_url=s.azure_openai_endpoint.rstrip("/"),
                        timeout=60.0, max_retries=1,
                    )
                else:
                    from openai import AzureOpenAI

                    self._client = AzureOpenAI(
                        api_key=s.azure_key,
                        azure_endpoint=s.azure_openai_endpoint,
                        api_version=s.azure_openai_api_version,
                        timeout=60.0, max_retries=1,
                    )
                self._kind, self._model = "openai", s.azure_openai_deployment

            elif provider == "gemini":
                if not s.gemini_api_key:
                    self._reason = "GEMINI_API_KEY is not set"
                    return
                import google.generativeai as genai

                genai.configure(api_key=s.gemini_api_key)
                self._client = genai.GenerativeModel(s.gemini_model)
                self._kind, self._model = "gemini", s.gemini_model
            else:
                self._reason = f"unknown provider '{provider}'"
                return

            self._reason = "ready"
        except Exception as exc:
            logger.warning("LLM init failed for provider %s: %s", provider, exc)
            self._client = None
            self._reason = f"initialisation failed: {exc}"

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._client is not None

    def status(self) -> LLMStatus:
        return LLMStatus(
            provider=self.settings.llm_provider, model=self._model,
            available=self.available, reason=self._reason,
        )

    # ------------------------------------------------------------------
    def complete(self, system: str, user: str, max_tokens: int = 1200) -> str | None:
        """Free-text completion. Returns None on any failure."""
        if not self.available:
            return None
        try:
            if self._kind == "openai":
                r = self._client.chat.completions.create(
                    model=self._model, max_tokens=max_tokens, temperature=0.2,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                return (r.choices[0].message.content or "").strip() or None
            r = self._client.generate_content(f"{system}\n\n{user}")
            return (getattr(r, "text", "") or "").strip() or None
        except Exception as exc:
            logger.warning("LLM completion failed: %s", exc)
            return None

    @property
    def supports_tools(self) -> bool:
        """Tool calling rides the OpenAI wire format only.

        Gemini's SDK exposes function calling through a different surface; until
        that is implemented the agent degrades to "unavailable" rather than
        silently pretending it reasoned over tools.
        """
        return self.available and self._kind == "openai"

    def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1200,
    ) -> ToolTurn | None:
        """One turn of a tool-calling conversation. Returns None on any failure.

        ``messages`` is the full running history in OpenAI wire format (system,
        user, assistant-with-tool_calls, tool results). Passing no ``tools``
        forces a prose answer, which is how the loop closes out at its cap.
        """
        if not self.supports_tools:
            return None
        try:
            kwargs: dict[str, Any] = {}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            r = self._client.chat.completions.create(
                model=self._model, max_tokens=max_tokens, temperature=0.0,
                messages=messages, **kwargs,
            )
            choice = r.choices[0]
            msg = choice.message
            content = (msg.content or "").strip() or None

            calls: list[ToolCall] = []
            wire_calls: list[dict] = []
            for tc in getattr(msg, "tool_calls", None) or []:
                raw = tc.function.arguments or "{}"
                try:
                    parsed = json.loads(raw)
                except (ValueError, TypeError):
                    logger.warning("Tool call %s had unparseable arguments", tc.function.name)
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}
                calls.append(ToolCall(id=tc.id, name=tc.function.name,
                                      arguments=parsed, raw_arguments=raw))
                wire_calls.append({
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": raw},
                })

            assistant: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if wire_calls:
                assistant["tool_calls"] = wire_calls

            return ToolTurn(
                content=content, tool_calls=calls, assistant_message=assistant,
                finish_reason=choice.finish_reason,
            )
        except Exception as exc:
            logger.warning("LLM tool-calling turn failed: %s", exc)
            return None

    def complete_json(
        self, system: str, user: str, schema: dict, max_tokens: int = 800
    ) -> dict | None:
        """Structured completion validated against ``schema``.

        Providers differ in how strictly they enforce a schema, so the result is
        validated locally regardless and ``None`` is returned if it does not fit.
        """
        if not self.available:
            return None
        instruction = (
            f"{system}\n\nRespond with a single JSON object only, no prose and no "
            f"code fences, matching this JSON schema:\n{json.dumps(schema)}"
        )
        try:
            if self._kind == "openai":
                r = self._client.chat.completions.create(
                    model=self._model, max_tokens=max_tokens, temperature=0.0,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": instruction},
                              {"role": "user", "content": user}],
                )
                raw = r.choices[0].message.content or ""
            else:
                r = self._client.generate_content(
                    f"{instruction}\n\n{user}",
                    generation_config={"response_mime_type": "application/json"},
                )
                raw = getattr(r, "text", "") or ""

            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].removeprefix("json").strip()
            data = json.loads(raw)
            return data if _fits(data, schema) else None
        except Exception as exc:
            logger.warning("LLM structured completion failed: %s", exc)
            return None


def _fits(data: Any, schema: dict) -> bool:
    """Minimal structural check: required keys present, object at the root."""
    if schema.get("type") == "object" and not isinstance(data, dict):
        return False
    for key in schema.get("required", []):
        if key not in data:
            return False
    return True


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_llm() -> None:
    """Test hook: drop the cached client so settings changes take effect."""
    global _client
    _client = None
