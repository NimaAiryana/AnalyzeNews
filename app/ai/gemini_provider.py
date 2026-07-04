"""Google Gemini (Google AI Studio) provider.

Uses the async `google-genai` client (`client.aio.models.generate_content`).
Google Search grounding and a configurable thinking level are enabled so the
model can verify/enrich the crawled news with live context.
"""

import asyncio
import logging

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.base import AIProvider
from app.config import Settings

logger = logging.getLogger(__name__)

# 🔄 Codes worth retrying: rate limit + transient server errors
_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_NETWORK = (httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, settings: Settings, model: str) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.model = model
        self._settings = settings
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        # 📤 Async call with retry on transient failures (429 / 5xx / network)
        config = self._build_config(system_prompt)
        attempts = max(1, self._settings.gemini_max_retries + 1)
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                return self._extract_text(resp)
            except Exception as exc:  # noqa: BLE001 - decide retryability below
                last_exc = exc
                if attempt < attempts and self._is_retryable(exc):
                    delay = self._settings.gemini_retry_delay_seconds * attempt
                    logger.warning(
                        "[%s] attempt %d/%d failed (%s); retrying in %.1fs",
                        self.model, attempt, attempts, self._describe(exc), delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        # 🎯 Retry rate-limit / transient server errors and network blips only
        if isinstance(exc, genai_errors.APIError):
            return getattr(exc, "code", None) in _RETRYABLE_CODES
        return isinstance(exc, _RETRYABLE_NETWORK)

    @staticmethod
    def _describe(exc: Exception) -> str:
        code = getattr(exc, "code", None)
        return f"{type(exc).__name__} {code}" if code else type(exc).__name__

    def _build_config(self, system_prompt: str) -> types.GenerateContentConfig:
        tools = None
        if self._settings.gemini_use_google_search:
            # 🔍 Live Google Search grounding
            tools = [types.Tool(google_search=types.GoogleSearch())]

        thinking = None
        level = (self._settings.gemini_thinking_level or "").strip().upper()
        if level and level != "THINKING_LEVEL_UNSPECIFIED":
            # 💡 Higher thinking level -> deeper reasoning before answering
            thinking = types.ThinkingConfig(thinking_level=level)

        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self._settings.gemini_temperature,
            top_p=self._settings.gemini_top_p,
            max_output_tokens=self._settings.gemini_max_output_tokens,
            tools=tools,
            thinking_config=thinking,
        )

    @staticmethod
    def _extract_text(resp) -> str:
        # 🔧 Prefer the convenience accessor; fall back to concatenating text parts
        text = getattr(resp, "text", None)
        if text:
            return text
        try:
            parts = resp.candidates[0].content.parts
            return "".join(getattr(p, "text", "") or "" for p in parts)
        except (AttributeError, IndexError, TypeError):
            return ""
