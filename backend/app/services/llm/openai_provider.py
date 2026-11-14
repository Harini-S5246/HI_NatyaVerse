"""OpenAI provider for evidence-grounded story generation (secondary/comparison)."""
from __future__ import annotations
import logging
from typing import Any
from app.config import settings
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest
logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Secondary/comparison story-generation provider using OpenAI."""

    name = "openai"

    def __init__(self) -> None:
        self._model_name = settings.openai_model
        self._client = None

    @property
    def model(self) -> str:
        return self._model_name

    def is_available(self) -> bool:
        if not settings.openai_api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        import openai

        self._client = openai.OpenAI(api_key=settings.openai_api_key)
        return self._client

    def generate_story(self, evidence: dict[str, Any], language: str) -> LLMResult:
        if not self.is_available():
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error="OPENAI_API_KEY is not configured or the SDK is not installed.",
            )
        prompt = _build_prompt(evidence, language)
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": "You are an evidence-grounded Bharatanatyam interpretation assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                return LLMResult(
                    text="",
                    provider=self.name,
                    model=self._model_name,
                    error="OpenAI returned an empty response.",
                )
            return LLMResult(text=text, provider=self.name, model=self._model_name, raw=response)
        except Exception as exc:  # noqa: BLE001 - surfaced as controlled error
            logger.warning("OpenAI story generation failed: provider=%s model=%s error_type=%s", self.name, self._model_name, type(exc).__name__)
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
            )

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        """Run the common validated request; evidence policy lives upstream."""
        if not self.is_available():
            return LLMResult(text="", provider=self.name, model=self._model_name, error="OPENAI_API_KEY is not configured or the SDK is not installed.")
        try:
            response = self._get_client().chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": "Return only the response requested by the supplied validated prompt."},
                    {"role": "user", "content": request.prompt},
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                return LLMResult(text="", provider=self.name, model=self._model_name, error="OpenAI returned an empty response.")
            return LLMResult(text=text, provider=self.name, model=self._model_name, raw=response)
        except Exception as exc:  # noqa: BLE001 - returned as controlled provider failure
            logger.warning("OpenAI structured generation failed: model=%s error_type=%s", self._model_name, type(exc).__name__)
            return LLMResult(text="", provider=self.name, model=self._model_name, error=f"{type(exc).__name__}: {exc}")


def _build_prompt(evidence: dict[str, Any], language: str) -> str:
    """Build the evidence-grounded prompt for OpenAI."""
    language_name = {
        "en": "English",
        "ta": "Tamil",
        "hi": "Hindi",
        "ml": "Malayalam",
    }.get(language, "English")

    import json

    evidence_json = json.dumps(evidence, ensure_ascii=False, indent=2)

    return f"""You are an evidence-grounded Bharatanatyam interpretation assistant.

You will be given a JSON object containing ONLY the recorded multimodal evidence
extracted from a real Bharatanatyam performance by the HI-Natya Verse system.

IMPORTANT — WHAT COUNTS AS VALID EVIDENCE:
- "grounded_evidence" contains source-backed knowledge-base meanings with their explicit verification status and provenance. "grounded" does not mean fully verified.
- "detected_evidence" contains model outputs, including predicted emotion labels; these are not classical Bhava or Rasa classifications.
- "unresolved_evidence" contains gestures detected by the model whose meanings are unavailable or pending. These must remain explicitly unresolved.
- If "detected_evidence" contains a predicted emotion label, describe it only as a model observation, not as classical Bhava or Rasa.

STRICT RULES:
- Use ONLY the supplied evidence. Do not invent anything.
- Do NOT invent Mudra meanings, Bharatanatyam facts, mythology, characters, lyrics, choreography, or semantic relationships.
- Do NOT convert unresolved evidence into verified meanings.
- Unresolved evidence must remain explicitly unresolved.
- Do NOT claim lyrics exist when the evidence says lyrics are null/absent.
- Do NOT claim a Mudra-Bhava relationship unless the evidence explicitly states one.
- Preserve Bharatanatyam technical terminology where appropriate.
- Clearly distinguish verified, partially verified, and unresolved knowledge-base evidence using the supplied status and provenance.
- Generate a coherent, meaningful narrative from the valid evidence.
- The narrative must be written entirely in {language_name}.

EVIDENCE (JSON):
{evidence_json}

Write the narrative now. It should be a flowing, meaningful interpretation of the
performance based strictly on the evidence above. Do not add a preamble or
explanation of these instructions — just the narrative.
"""
