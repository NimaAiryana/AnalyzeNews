"""Google Gemini (Google AI Studio) provider.

Uses the async `google-genai` client (`client.aio.models.generate_content`).
Google Search grounding and a configurable thinking level are enabled so the
model can verify/enrich the crawled news with live context.
"""

import logging

from google import genai
from google.genai import types

from app.ai.base import AIProvider
from app.config import Settings

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, settings: Settings, model: str) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.model = model
        self._settings = settings
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        # 📤 Async, non-blocking call so Flash and Pro can run concurrently
        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=self._build_config(system_prompt),
        )
        return self._extract_text(resp)

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
