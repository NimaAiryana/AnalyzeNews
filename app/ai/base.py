"""Abstract AI provider interface so OpenAI / Anthropic are interchangeable."""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Every provider returns raw model text for a (system, user) prompt pair."""

    name: str
    model: str

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send the prompt to the model and return the raw text response."""
        raise NotImplementedError
