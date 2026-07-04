"""Factory that builds the configured AI provider."""

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIProvider
from app.ai.openai_provider import OpenAIProvider
from app.config import Settings


def build_ai_provider(settings: Settings) -> AIProvider:
    provider = (settings.ai_provider or "openai").strip().lower()
    if provider == "openai":
        return OpenAIProvider(settings)
    if provider == "anthropic":
        return AnthropicProvider(settings)
    raise ValueError(f"Unsupported AI_PROVIDER '{settings.ai_provider}' (use 'openai' or 'anthropic')")
