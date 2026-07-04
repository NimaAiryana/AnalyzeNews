"""Anthropic (Claude) provider implementation."""

import logging

from anthropic import AsyncAnthropic

from app.ai.base import AIProvider
from app.config import Settings

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.model = settings.anthropic_model
        self._max_tokens = settings.ai_max_tokens
        self._temperature = settings.ai_temperature
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        # 💡 Claude returns JSON when instructed; we nudge it with a priming assistant turn
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": "{"},
            ],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        # Re-attach the opening brace we primed the assistant with
        return text if text.strip().startswith("{") else "{" + text
