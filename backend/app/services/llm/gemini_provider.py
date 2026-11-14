"""Gemini provider for evidence-grounded story generation."""
from __future__ import annotations

import base64
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest

logger = logging.getLogger(__name__)
_REQUEST_TIMEOUT_SECONDS = 60
_MAX_TOKENS_FINISH_REASON = 2


def _rate_limit_details(exc: Exception) -> tuple[int | None, str | None]:
    """Extract a safe retry hint from Gemini's ResourceExhausted response."""
    detail = str(exc)
    if "429" not in detail and "ResourceExhausted" not in detail:
        return None, None
    duration_match = re.search(
        r"retry in\s+((?:\d+(?:\.\d+)?h)?(?:\d+(?:\.\d+)?m)?(?:\d+(?:\.\d+)?s))",
        detail,
        flags=re.IGNORECASE,
    )
    if duration_match:
        unit_seconds = {"h": 3600, "m": 60, "s": 1}
        seconds = sum(
            float(value) * unit_seconds[unit.lower()]
            for value, unit in re.findall(
                r"(\d+(?:\.\d+)?)([hms])",
                duration_match.group(1),
                flags=re.IGNORECASE,
            )
        )
        return max(1, math.ceil(seconds)), "GEMINI_RATE_LIMITED"
    patterns = (
        r"retry[_ ]delay[^0-9]*(\d+(?:\.\d+)?)\s*s",
        r"retry after[^0-9]*(\d+(?:\.\d+)?)\s*(?:seconds?|s)?",
    )
    for pattern in patterns:
        match = re.search(pattern, detail, flags=re.IGNORECASE)
        if match:
            return max(1, int(float(match.group(1)))), "GEMINI_RATE_LIMITED"
    return None, "GEMINI_RATE_LIMITED"


def _request_error_code(exc: Exception) -> str:
    error_type = type(exc).__name__.lower()
    if "timeout" in error_type or "deadlineexceeded" in error_type:
        return "GEMINI_TIMEOUT"
    if any(marker in error_type for marker in ("connection", "serviceunavailable", "internalserver")):
        return "GEMINI_CONNECTION_FAILED"
    return "GEMINI_REQUEST_FAILED"


class GeminiProvider(LLMProvider):
    """Primary story-generation provider using Google Gemini."""

    name = "gemini"

    def __init__(self) -> None:
        self._model_name = settings.gemini_model
        self._client = None

    @property
    def model(self) -> str:
        return self._model_name

    def is_available(self) -> bool:
        if not settings.gemini_api_key:
            return False
        try:
            import google.generativeai as genai  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._client = genai.GenerativeModel(self._model_name)
        return self._client

    def generate_story(self, evidence: dict[str, Any], language: str) -> LLMResult:
        if not self.is_available():
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error="GEMINI_API_KEY is not configured or the SDK is not installed.",
            )
        prompt = _build_prompt(evidence, language)
        try:
            client = self._get_client()
            response = client.generate_content(
                prompt,
                request_options={"timeout": _REQUEST_TIMEOUT_SECONDS},
            )
            text = (response.text or "").strip()
            if not text:
                return LLMResult(
                    text="",
                    provider=self.name,
                    model=self._model_name,
                    error="Gemini returned an empty response.",
                )
            return LLMResult(text=text, provider=self.name, model=self._model_name, raw=response)
        except Exception as exc:  # noqa: BLE001 - surfaced as controlled error
            logger.warning("Gemini story generation failed: provider=%s model=%s error_type=%s", self.name, self._model_name, type(exc).__name__)
            retry_after, error_code = _rate_limit_details(exc)
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
                retry_after_seconds=retry_after,
                error_code=error_code,
)
    
    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        """Run the common validated request; evidence policy lives upstream."""
        if not self.is_available():
            return LLMResult(text="", provider=self.name, model=self._model_name, error="GEMINI_API_KEY is not configured or the SDK is not installed.")
        video_id = request.video_id or "unknown"
        evidence_items = request.evidence_items if request.evidence_items is not None else 0
        started = time.monotonic()
        logger.info(
            "[STORY_GEMINI] video_id=%s model=%s evidence_items=%s prompt_chars=%s request_started",
            video_id,
            self._model_name,
            evidence_items,
            len(request.prompt),
        )
        try:
            response = self._get_client().generate_content(
                request.prompt,
                generation_config={
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_tokens,
                    "response_mime_type": "application/json",
                    "response_schema": dict(request.response_schema) if request.response_schema else None,
                },
                request_options={"timeout": _REQUEST_TIMEOUT_SECONDS, "retry": None},
            )
            structured_output = _extract_json_from_gemini_response(response)
            response_texts = _response_texts(response)
            response_chars = (
                len(json.dumps(structured_output, ensure_ascii=False))
                if isinstance(structured_output, dict)
                else sum(len(text) for text in response_texts)
            )
            elapsed = time.monotonic() - started
            candidates = _value(response, "candidates") or []
            finish_reason = _value(candidates[0], "finish_reason") if candidates else None
            truncated = (
                finish_reason == _MAX_TOKENS_FINISH_REASON
                or str(finish_reason).upper().endswith("MAX_TOKENS")
            )
            logger.info(
                "[STORY_GEMINI] video_id=%s model=%s request_completed elapsed_seconds=%.2f response_chars=%s finish_reason=%s",
                video_id,
                self._model_name,
                elapsed,
                response_chars,
                finish_reason,
            )
            if structured_output is None:
                error_code = "GEMINI_OUTPUT_TRUNCATED" if truncated else "GEMINI_EMPTY_RESPONSE"
                message = "Gemini stopped at the output-token limit before returning complete JSON." if truncated else "Gemini returned an empty response."
                return LLMResult(text="", provider=self.name, model=self._model_name, raw=response, error=message, error_code=error_code)
            if structured_output is _INVALID_JSON:
                if truncated:
                    return LLMResult(
                        text="",
                        provider=self.name,
                        model=self._model_name,
                        raw=response,
                        error="Gemini stopped at the output-token limit before returning complete JSON.",
                        error_code="GEMINI_OUTPUT_TRUNCATED",
                    )
                return LLMResult(
                    text="",
                    provider=self.name,
                    model=self._model_name,
                    raw=response,
                    error="Gemini returned invalid structured JSON.",
                    error_code="GEMINI_INVALID_JSON",
                )
            # The package-aware, provider-independent validator is invoked by
            # narrative_generation_service with this parsed object.
            return LLMResult(
                text=json.dumps(structured_output, ensure_ascii=False),
                provider=self.name,
                model=self._model_name,
                raw=response,
                structured_output=structured_output,
            )
        except Exception as exc:  # noqa: BLE001 - returned as controlled provider failure
            elapsed = time.monotonic() - started
            logger.error(
                "[STORY_GEMINI_ERROR] error_type=%s elapsed_seconds=%.2f model=%s video_id=%s",
                type(exc).__name__,
                elapsed,
                self._model_name,
                video_id,
            )
            retry_after, error_code = _rate_limit_details(exc)
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
                retry_after_seconds=retry_after,
                error_code=error_code or _request_error_code(exc),
            )

    def generate_visual_story(
        self,
        prompt: str,
        frame_paths: list[Path],
        temperature: float = 0.4,
        max_tokens: int = 2000,
    ) -> LLMResult:
        """Generate a visual story from frames and prompt using Gemini multimodal."""
        if not self.is_available():
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error="GEMINI_API_KEY is not configured or the SDK is not installed.",
            )
        try:
            client = self._get_client()
            
            # Prepare content parts: prompt + images
            content_parts = [prompt]
            for frame_path in frame_paths:
                if frame_path.is_file():
                    with open(frame_path, "rb") as f:
                        image_data = f.read()
                    content_parts.append({
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(image_data).decode("utf-8"),
                    })
            
            response = client.generate_content(
                content_parts,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
                request_options={"timeout": _REQUEST_TIMEOUT_SECONDS},
            )
            text = (response.text or "").strip()
            if not text:
                return LLMResult(
                    text="",
                    provider=self.name,
                    model=self._model_name,
                    error="Gemini returned an empty response.",
                )
            return LLMResult(text=text, provider=self.name, model=self._model_name, raw=response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini visual story generation failed: model=%s error_type=%s", self._model_name, type(exc).__name__)
            retry_after, error_code = _rate_limit_details(exc)
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
                retry_after_seconds=retry_after,
                error_code=error_code,
            )


_JSON_FENCE = re.compile(r"^```[^\r\n]*\r?\n(.*?)\r?\n```$", re.IGNORECASE | re.DOTALL)
_INVALID_JSON = object()


def _strip_json_fence(text: str) -> str:
    """Remove only an outer Markdown fence; leave all JSON content intact."""
    stripped = text.strip()
    match = _JSON_FENCE.match(stripped)
    return match.group(1).strip() if match else stripped


def _extract_json_from_gemini_response(response: Any) -> dict[str, Any] | object | None:
    """Return one Gemini JSON object without accepting prose or repairing it.

    ``google.generativeai`` exposes a convenience ``response.text`` property,
    but that property can raise when candidates/parts are not singular.  Its
    native response is candidate -> content -> parts, and newer SDK response
    objects may expose an already-parsed mapping.  All paths below preserve
    the complete selected candidate before doing the same strict JSON decode.
    """
    parsed = _value(response, "parsed")
    if isinstance(parsed, Mapping):
        return dict(parsed)
    if parsed is not None:
        return _INVALID_JSON

    texts = _response_texts(response)
    if not texts:
        return None
    for text in texts:
        try:
            value = json.loads(_strip_json_fence(text))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
        return _INVALID_JSON
    return _INVALID_JSON


def _response_texts(response: Any) -> list[str]:
    """Collect complete textual candidate content from real SDK response shapes."""
    texts: list[str] = []
    try:
        text = _value(response, "text")
    except Exception:  # Gemini raises for responses without a text candidate.
        text = None
    if isinstance(text, str) and text.strip():
        texts.append(text.strip())

    # In the installed legacy SDK, ``to_dict`` is the lossless supported
    # representation of the underlying proto.  It also makes this tolerant
    # of client wrappers that return mappings instead of proto objects.
    response_mapping = response if isinstance(response, Mapping) else _to_dict(response)
    candidates = _value(response_mapping, "candidates") or _value(response, "candidates") or []
    for candidate in candidates:
        parts = _value(_value(candidate, "content"), "parts") or []
        fragments = [
            part_text for part in parts
            if isinstance((part_text := _value(part, "text")), str) and part_text
        ]
        if fragments:
            joined = "\n".join(fragments).strip()
            if joined and joined not in texts:
                texts.append(joined)
    return texts


def _to_dict(response: Any) -> Mapping[str, Any] | None:
    try:
        value = response.to_dict()
    except (AttributeError, TypeError, ValueError):
        return None
    return value if isinstance(value, Mapping) else None


def _value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    try:
        return getattr(value, name, None)
    except (AttributeError, TypeError, ValueError):
        return None


def _build_prompt(evidence: dict[str, Any], language: str) -> str:
    """Build a story-generation prompt from verified temporal evidence."""

    language_name = {
        "en": "English",
        "ta": "Tamil",
        "hi": "Hindi",
        "ml": "Malayalam",
    }.get(language, "English")

    import json

    evidence_json = json.dumps(
        evidence,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
You are the STORY GENERATION ENGINE of HI-Natya Verse.

Your job is to convert source-backed performance observations and
knowledge-base meanings with their explicit verification status into
a simple, natural, human-readable STORY.

The user does NOT want a research report.
The user does NOT want a list of Mudras.
The user does NOT want confidence percentages.
The user wants to understand:

"What is happening through this dance?"

For example, a good output style is:

"Krishna enters the forest and sees Radha. He feels love and happiness.
When Krishna leaves, Radha becomes angry and expresses her sadness."

However, this is ONLY an example of writing style.
You MUST NOT use Krishna, Radha, forest, love, or any other event
unless the supplied evidence actually supports it.

==================================================
EVIDENCE RULES
==================================================

The supplied JSON comes from the actual uploaded video.

You may use:

1. temporal_events
   - These describe what was detected and WHEN it appeared.
   - Preserve their chronological order.

2. grounded_evidence
   - These contain source-backed knowledge-base meanings and their explicit
     verification status. "grounded" does not mean fully verified.
   - Use a meaning only when its claim ID, source references, and verification
     status are present, and retain the supplied status.

3. bhava_events
   - These are generic predicted emotion labels from a facial-expression model.
   - Describe them only as model observations, not classical Bhava or Rasa.

4. unresolved_evidence
   - These gestures have no reliable knowledge-base meaning available.
   - NEVER invent their meaning.

==================================================
STRICT ANTI-HALLUCINATION RULES
==================================================

- Use ONLY information contained in the supplied JSON.
- NEVER invent characters.
- NEVER invent names.
- NEVER invent places.
- NEVER invent mythology.
- NEVER invent relationships.
- NEVER invent dialogue.
- NEVER invent lyrics.
- NEVER invent events that are not supported.
- NEVER invent a Mudra meaning.
- NEVER assign meaning to unresolved Mudras.
- NEVER create a Mudra-Bhava relationship unless explicitly supplied.
- Temporal co-occurrence or overlap is observation metadata, not evidence of a cultural relationship.
- NEVER treat an uncertain prediction as a confirmed event.
- NEVER claim that lyrics exist when lyrics are unavailable.
- NEVER mention internal evidence IDs.
- NEVER mention model IDs.
- NEVER mention confidence percentages in the story.
- NEVER write an academic/research report.

==================================================
HOW TO WRITE THE STORY
==================================================

Follow the chronological order of the dance.

Do NOT simply write:

"Alapadmam means lotus.
Anjali means salutation.
Hamsasyam means swan."

Instead, describe knowledge-base meanings with their supplied verification status.

For example:

"The performance begins with a graceful lotus-like gesture,
creating a gentle opening. The dancer then brings the hands
together in a respectful salutation."

This is the desired style.

If the evidence supports only gestures and generic predicted emotion labels, then the story
must remain at that level.

For example:

"The performance begins with a graceful gesture resembling a blooming
lotus. The dancer then moves into a respectful salutation. As the dance
continues, the expressions shift toward a more emotional state, giving
the performance a changing and expressive character."

Do NOT force a fictional plot when the evidence does not support one.

==================================================
BHAVA HANDLING
==================================================

If a predicted emotion label is present:

- Refer to it only as a facial-expression model observation.
- Do not describe it as a classical Bhava or Rasa or as a verified inner state.
- Do NOT claim to know the dancer's private intention.

Example:

"The dancer's expressions gradually take on a sad and reflective
quality."

NOT:

"The dancer is heartbroken because her lover abandoned her."

The second statement invents a cause.

==================================================
UNRESOLVED GESTURES
==================================================

If unresolved gestures exist, do NOT interpret them.

Do not interrupt the main story repeatedly with technical warnings.

At the END, add one short sentence:

"Some gestures could not be interpreted confidently from the current
knowledge base."

==================================================
OUTPUT FORMAT
==================================================

Return ONLY the following:

TITLE:
A short natural title related to the actual evidence.

STORY:
Write 2–5 short paragraphs.

The story must answer:

- How does the dance begin?
- What happens as the dance progresses?
- How do the gestures and generic facial-expression observations change?
- How does the performance conclude, if the evidence supports a conclusion?

ENDING:
Write 1 short sentence describing the overall feeling of the
performance based only on the detected evidence.

==================================================
LANGUAGE
==================================================

Write the complete output in {language_name}.

Do not mix languages.

==================================================
IMPORTANT
==================================================

The result should feel like:

"A person explaining what they understood from watching the dance."

It should NOT feel like:

"An AI explaining its classification results."

==================================================
VERIFIED PERFORMANCE EVIDENCE
==================================================

{evidence_json}

==================================================

Generate the story now.
"""
