"""Abstract base for LLM story-generation providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


# This is the wire shape produced by a structured Story provider.  It is not
# the public narrative-generation response schema: provider-neutral validation
# adds the package-derived metadata after checking this object against the
# eligible evidence.
STORY_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "narrative": {"type": "string"},
        "used_event_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "narrative", "used_event_ids"],
}


@dataclass
class LLMResult:
    """Normalized result from any LLM provider."""

    text: str
    provider: str
    model: str
    raw: Any = None
    error: str | None = None
    structured_output: dict[str, Any] | None = None
    retry_after_seconds: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class StructuredGenerationRequest:
    """Provider-neutral request built only after evidence validation."""

    prompt: str
    temperature: float = 0.2
    max_tokens: int = 700
    video_id: str | None = None
    evidence_items: int | None = None
    # Provider adapters may use this transport-level schema where their SDK
    # supports constrained JSON output.  Validation remains provider-neutral.
    response_schema: Mapping[str, Any] | None = None


class LLMProvider(ABC):
    """Transport adapter for an already-validated story-generation request.

    Providers receive no analysis artifacts or evidence packages.  Prompt
    construction and all validation remain with the live narration boundary.
    """

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider can be invoked (key present, SDK installed)."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the configured model identifier without making a request."""

    @abstractmethod
    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        """Return output for one provider-neutral, already-safe request."""
