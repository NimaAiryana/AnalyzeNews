"""OpenAI (ChatGPT) provider implementation."""

import logging

from openai import AsyncOpenAI

from app.ai.base import AIProvider
from app.config import Settings

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.model = settings.openai_model
        self._max_tokens = settings.ai_max_tokens
        self._temperature = settings.ai_temperature
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        # 📤 Request JSON output so the analysis service can parse structured fields
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or ""
