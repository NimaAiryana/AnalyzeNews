"""Factory helpers that build the configured Gemini providers."""

from app.ai.gemini_provider import GeminiProvider
from app.config import Settings


def build_gemini_pro(settings: Settings) -> GeminiProvider:
    # 🎯 Deep model: used both in stage 1 and for the final combined verdict
    return GeminiProvider(settings, settings.gemini_pro_model)


def build_gemini_flash(settings: Settings) -> GeminiProvider:
    # ⚡ Fast model: runs in parallel with Pro during stage 1
    return GeminiProvider(settings, settings.gemini_flash_model)
