"""Ollama provider for local story generation.

HI-Natya Verse
--------------
Uses a locally running Ollama model to convert source-backed temporal
Bharatanatyam evidence into a human-readable story.

The provider:
- Uses ONLY the supplied evidence package.
- Preserves chronological order.
- Does not invent mythology, characters, lyrics, or relationships.
- Does not assign meanings to unresolved Mudras.
- Distinguishes high-confidence evidence from weak evidence.
- Produces a simple story rather than a technical evidence report.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local LLM provider using Ollama."""

    name = "ollama"

    def __init__(self) -> None:
        self._model_name = "qwen2.5-coder:3b"
        self._base_url = "http://127.0.0.1:11434"

    @property
    def model(self) -> str:
        return self._model_name

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True when Ollama is running and the configured model exists."""

        try:
            response = requests.get(
                f"{self._base_url}/api/tags",
                timeout=3,
            )

            if response.status_code != 200:
                return False

            data = response.json()
            models = data.get("models", [])

            return any(
                model.get("name") == self._model_name
                for model in models
            )

        except requests.RequestException:
            return False

        except Exception:
            return False

    # ------------------------------------------------------------------
    # Story generation
    # ------------------------------------------------------------------

    def generate_story(
        self,
        evidence: dict[str, Any],
        language: str,
    ) -> LLMResult:
        """Generate an evidence-grounded narrative using Ollama."""

        prompt = _build_ollama_story_prompt(
            evidence=evidence,
            language=language,
        )
        return self.generate_prompt(prompt, evidence=evidence)

    def generate_prompt(
        self,
        prompt: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Backward-compatible wrapper for a caller-built prompt."""
        return self.generate(StructuredGenerationRequest(prompt=prompt))

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        """Run the common structured-generation request against Ollama."""
        if not self.is_available():
            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=(
                    "Ollama is unavailable or "
                    f"{self._model_name} is not installed."
                ),
            )

        payload = {
            "model": self._model_name,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                # Low temperature keeps the story grounded.
                "temperature": request.temperature,

                # Prevent excessively long research-style responses.
                "num_predict": request.max_tokens,
            },
        }

        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

            data = response.json()

            text = (data.get("response") or "").strip()

            if not text:
                return LLMResult(
                    text="",
                    provider=self.name,
                    model=self._model_name,
                    error="Ollama returned an empty response.",
                )

            return LLMResult(
                text=text,
                provider=self.name,
                model=self._model_name,
                raw=data,
            )

        except requests.RequestException as exc:
            logger.warning(
                "Ollama request failed: model=%s video_id=%s error=%s",
                self._model_name,
                (evidence or {}).get("video_id"),
                exc,
            )

            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"RequestException: {exc}",
            )

        except Exception as exc:
            logger.warning(
                "Ollama story generation failed: "
                "model=%s video_id=%s error_type=%s",
                self._model_name,
                (evidence or {}).get("video_id"),
                type(exc).__name__,
            )

            return LLMResult(
                text="",
                provider=self.name,
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
            )


# ======================================================================
# PROMPT BUILDER
# ======================================================================

def _build_ollama_story_prompt(
    evidence: dict[str, Any],
    language: str,
) -> str:
    """
    Build a STRICT evidence-only story prompt for small Ollama models.

    Important:
    This prompt intentionally limits creativity because small models may
    hallucinate scenes, emotions, characters, actions, and meanings.
    """

    language_name = {
        "en": "English",
        "ta": "Tamil",
        "hi": "Hindi",
        "ml": "Malayalam",
    }.get(language, "English")

    # --------------------------------------------------------------
    # Extract evidence
    # --------------------------------------------------------------

    video_id = evidence.get("video_id")

    summary = evidence.get("summary", {})

    temporal_events = evidence.get("narrative_events", [])
    bhava_events = evidence.get("bhava_events", [])

    grounded_evidence = evidence.get(
        "grounded_evidence",
        [],
    )

    unresolved_evidence = evidence.get(
        "unresolved_evidence",
        [],
    )

    # --------------------------------------------------------------
    # Sort events by actual time
    # --------------------------------------------------------------

    def event_start(event: dict[str, Any]) -> float:
        value = event.get("start_time")

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    temporal_events = sorted(
        temporal_events,
        key=event_start,
    )

    # --------------------------------------------------------------
    # Build VERIFIED Mudra lookup
    # --------------------------------------------------------------

    knowledge_meanings: dict[str, dict[str, Any]] = {}

    for item in grounded_evidence:

        label = item.get("label")
        detail = item.get("meaning") or item.get("detail")
        verification_status = item.get("verification_status")
        source_references = item.get("source_references")
        uncertainty_notes = item.get("uncertainty_notes")

        if (
            not label
            or not detail
            or verification_status not in {"verified", "partially_verified"}
            or item.get("knowledge_status", verification_status) != verification_status
            or not isinstance(item.get("claim_id"), str)
            or not item["claim_id"].strip()
            or not isinstance(source_references, list)
            or not source_references
            or any(not isinstance(reference, str) or not reference.strip() for reference in source_references)
            or not isinstance(uncertainty_notes, list)
            or any(not isinstance(note, str) for note in uncertainty_notes)
        ):
            continue

        knowledge_meanings[label.lower()] = {
            "label": label,
            "meaning": detail,
            "confidence": item.get("confidence"),
            "id": item.get("id"),
            "knowledge_status": item.get("knowledge_status", verification_status),
            "verification_status": verification_status,
            "claim_id": item["claim_id"],
            "source_references": source_references,
            "uncertainty_notes": uncertainty_notes,
        }

    # --------------------------------------------------------------
    # Build temporal evidence
    # --------------------------------------------------------------

    clean_temporal_events = []

    for event in temporal_events:

        mudra = event.get("mudra")

        if not mudra:
            continue

        knowledge = knowledge_meanings.get(
            str(mudra).lower()
        )

        clean_temporal_events.append(
            {
                "mudra": mudra,
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
                "duration": event.get("duration"),
                "confidence": event.get("mudra_confidence"),
                "bhava": event.get("bhava"),
                "bhava_confidence": event.get("bhava_confidence"),
                "knowledge_meaning": (
                    knowledge["meaning"]
                    if knowledge
                    else None
                ),
                "knowledge_status": knowledge.get("knowledge_status") if knowledge else None,
                "verification_status": knowledge.get("verification_status") if knowledge else None,
                "claim_id": knowledge.get("claim_id") if knowledge else None,
                "source_references": knowledge.get("source_references", []) if knowledge else [],
                "uncertainty_notes": knowledge.get("uncertainty_notes", []) if knowledge else [],
                "semantic_grounding_status": event.get("semantic_grounding_status"),
                "evidence_ids": event.get("evidence_ids", []),
            }
        )

    # --------------------------------------------------------------
    # Bhava evidence
    # --------------------------------------------------------------

    clean_bhava_events = []

    for event in bhava_events:

        label = event.get("label")

        if not label:
            continue

        clean_bhava_events.append(
            {
                "label": label,
                "confidence": event.get("confidence"),
            }
        )

    # --------------------------------------------------------------
    # Verified evidence
    # --------------------------------------------------------------

    clean_knowledge = []

    for item in grounded_evidence:

        label = item.get("label")
        detail = item.get("meaning") or item.get("detail")

        if not label or not detail or label.lower() not in knowledge_meanings:
            continue

        clean_knowledge.append(knowledge_meanings[label.lower()])

    # --------------------------------------------------------------
    # Unresolved evidence
    # --------------------------------------------------------------

    clean_unresolved = []

    for item in unresolved_evidence:

        if isinstance(item, dict):

            label = item.get("label")

            if label:
                clean_unresolved.append(label)

        else:

            clean_unresolved.append(
                str(item)
            )

    # --------------------------------------------------------------
    # VERY SMALL INPUT
    #
    # Small models work better when irrelevant fields are removed.
    # --------------------------------------------------------------

    story_input = {
        "video_id": video_id,

        "duration_seconds": summary.get(
            "duration_seconds"
        ),

        "temporal_mudra_events": clean_temporal_events,

        "narrative_events": clean_temporal_events,

        "detected_bhava_events": clean_bhava_events,

        "mudra_knowledge_meanings": clean_knowledge,

        "unresolved_gestures": clean_unresolved,
    }

    evidence_json = json.dumps(
        story_input,
        ensure_ascii=False,
        indent=2,
    )

    # ==============================================================
    # STRICT PROMPT
    # ==============================================================

    return f"""
You are a factual language layer for HI-Natya Verse.

Treat the supplied evidence JSON as the sole source of factual truth.
Do not infer facts that are not explicitly present.
If evidence records the Neutral emotion label, do not output a different predicted emotion label.
If a fact is missing, omit it.
Do not create a narrative plot.
Do not invent causes, consequences, characters, audience reactions, or emotions.
Do not invent mythology, relationships, intentions, or unsupported symbolism.
Do not invent facial expressions, eyes, smiles, music, melody, atmosphere, pain, suffering, longing, farewell, or audience behavior.
Do not assign a meaning to a Mudra unless the evidence explicitly provides a knowledge-base meaning with its verification status and source provenance.
If a Mudra is unresolved, do not state its meaning.
Do not output headings such as "Opening paragraph", "Development paragraph", "Emotional paragraph", or "Closing paragraph".
Return plain prose only.

RULES
1. Every fact must come directly from the supplied evidence JSON.
2. Use predicted emotion labels only as generic facial-expression observations.
3. Use a Mudra meaning only when it is explicitly present with knowledge status, claim ID, source references, and uncertainty notes.
4. Do not describe predicted emotion labels as classical Bhava or Rasa classifications.
5. If evidence does not mention an audience, do not mention an audience.
6. If evidence does not mention a character, do not invent a character.
7. If evidence does not mention an action sequence, do not invent one.
8. If evidence does not mention a gesture, do not mention it.
9. Do not include confidence percentages, JSON, markdown, or model names.
10. Write approximately 2 to 4 natural sentences.
11. Summarize the knowledge-base evidence with its verification status instead of repeating every detailed
    interpretation; the interface displays those details separately.
12. Do not list confidence values or unresolved gesture names in the story;
    unresolved evidence is displayed separately.
13. Use the chronological narrative events to describe the observed sequence.
14. A richer narrative is allowed only when an event explicitly contains
    verified narrative context; otherwise describe the supplied knowledge-base meaning with its verification status and generic predicted emotion labels only.
15. Do not turn a gesture meaning into an action, character, place, relationship,
    intention, cause, or consequence.
16. Keep Mudra knowledge and facial-expression observations separate; temporal overlap does not establish a cultural relationship.

VERIFIED PERFORMANCE EVIDENCE
{evidence_json}

Write only the final evidence-grounded prose in {language_name}. No preamble, no headings, no invented content.
""".strip()
