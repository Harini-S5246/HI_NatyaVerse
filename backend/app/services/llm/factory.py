"""Provider factory for LLM story generation."""
from __future__ import annotations

from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.ollama_provider import OllamaProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Return a provider instance by name (defaults to production Gemini)."""
    provider_name = (name or settings.story_llm_provider or "gemini").strip().lower()
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
    return provider_cls()


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())
