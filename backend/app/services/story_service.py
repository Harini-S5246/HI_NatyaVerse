"""Evidence-grounded story generation for HI-Natya Verse.

This service sits after multimodal fusion.

Pipeline:

    Video
      ↓
    Mudra + Bhava + Pose
      ↓
    Fusion
      ↓
    Evidence
      ↓
    Temporal Story Input
      ↓
    LLM (Ollama / Gemini / OpenAI)
      ↓
    Human-readable Story

Rules:
- Only the current video's fusion result is used.
- Use Mudra knowledge-base meanings only with their explicit verification status and provenance.
- Treat classifier emotion labels as generic facial-expression observations, not classical Bhava or Rasa.
- Unresolved Mudras are never given invented meanings.
- No mythology, characters, lyrics, relationships, or events are invented.
- Temporal order is preserved.
- The generated output should read like a story, not a research report.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.errors import AppError
from app.config import settings
from app.services.llm import get_provider
from app.services.result_service import (
    get_modality_result,
    save_modality_result,
)

logger = logging.getLogger(__name__)


SUPPORTED_LANGUAGES = {"en", "ta", "hi", "ml"}


LANGUAGE_ALIASES = {
    "en": "en",
    "english": "en",

    "ta": "ta",
    "tamil": "ta",

    "hi": "hi",
    "hindi": "hi",

    "ml": "ml",
    "malayalam": "ml",
}


# ============================================================================
# LANGUAGE
# ============================================================================

def _normalize_language(language: str) -> str:
    """Return the canonical language code."""

    language = (language or "en").strip().lower()

    code = LANGUAGE_ALIASES.get(language)

    if code is None or code not in SUPPORTED_LANGUAGES:
        raise AppError(
            f"Unsupported language: {language}. "
            "Supported: en, ta, hi, ml.",
            400,
            "UNSUPPORTED_LANGUAGE",
        )

    return code


# ============================================================================
# EVIDENCE PACKAGE
# ============================================================================

def _build_evidence_package(fusion: dict) -> dict[str, Any]:
    """Build a chronological evidence package for the LLM.

    IMPORTANT:
    The LLM receives temporal events rather than only a bag of Mudra names.

    This allows the story generator to understand:

        beginning → middle → ending

    without inventing an artificial sequence.
    """

    evidence = fusion.get("evidence", {}) or {}

    summary = fusion.get("summary", {}) or {}

    timeline = fusion.get("timeline", []) or []

    grounded = evidence.get("grounded", []) or []

    detected = evidence.get("detected", []) or []

    unresolved = evidence.get("unresolved", []) or []


    # ------------------------------------------------------------------
    # Source-backed Mudra knowledge lookup
    # ------------------------------------------------------------------

    grounded_meanings: dict[str, dict[str, Any]] = {}

    for item in grounded:

        if not isinstance(item, dict):
            continue

        label = item.get("label")
        detail = item.get("detail")

        verification_status = item.get("verification_status")
        knowledge_status = item.get("knowledge_status")
        source_references = item.get("source_references")
        uncertainty_notes = item.get("uncertainty_notes")
        claim_id = item.get("claim_id")
        if (
            not label
            or not detail
            or verification_status not in {"verified", "partially_verified"}
            or knowledge_status != verification_status
            or not isinstance(claim_id, str)
            or not claim_id.strip()
            or not isinstance(source_references, list)
            or not source_references
            or any(not isinstance(reference, str) or not reference.strip() for reference in source_references)
            or not isinstance(uncertainty_notes, list)
            or any(not isinstance(note, str) for note in uncertainty_notes)
        ):
            continue

        grounded_meanings[label] = {
            "meaning": detail,
            "confidence": item.get("confidence"),
            "evidence_id": item.get("id"),
            "knowledge_status": knowledge_status,
            "verification_status": verification_status,
            "claim_id": claim_id,
            "source_references": source_references,
            "uncertainty_notes": uncertainty_notes,
        }


    # ------------------------------------------------------------------
    # Chronological Mudra events
    # ------------------------------------------------------------------

    temporal_events: list[dict[str, Any]] = []

    for row in timeline:

        if not isinstance(row, dict):
            continue

        mudra = row.get("mudra")

        if not mudra:
            continue

        event = {
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "mudra": mudra,
            "confidence": row.get("mudra_confidence"),
            "bhava": row.get("bhava"),
            "bhava_confidence": row.get("bhava_confidence"),
            "grounded": bool(
                row.get("mudra_grounded", False)
            ),
            "knowledge_meaning": None,
            "knowledge_status": None,
            "verification_status": None,
            "claim_id": None,
            "source_references": [],
            "uncertainty_notes": [],
        }

        # A legacy grounded flag is insufficient without source-backed status.
        if mudra in grounded_meanings:
            meaning_record = grounded_meanings[mudra]
            event.update({
                "knowledge_meaning": meaning_record["meaning"],
                "knowledge_status": meaning_record["knowledge_status"],
                "verification_status": meaning_record["verification_status"],
                "claim_id": meaning_record["claim_id"],
                "source_references": meaning_record["source_references"],
                "uncertainty_notes": meaning_record["uncertainty_notes"],
            })

        temporal_events.append(event)


    # ------------------------------------------------------------------
    # Sort events chronologically
    # ------------------------------------------------------------------

    def _start_time(event: dict[str, Any]) -> float:

        value = event.get("start_time")

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    temporal_events.sort(key=_start_time)

    narrative_events: list[dict[str, Any]] = []
    seen_narrative_facts: set[tuple[str, str]] = set()
    for event in temporal_events:
        if not event.get("knowledge_meaning"):
            continue
        fact_key = (
            str(event.get("mudra")),
            str(event.get("knowledge_meaning")),
        )
        if fact_key in seen_narrative_facts:
            continue
        seen_narrative_facts.add(fact_key)
        narrative_event = {
            "start_time": event.get("start_time"),
            "end_time": event.get("end_time"),
            "duration": (
                float(event["end_time"]) - float(event["start_time"])
                if event.get("start_time") is not None
                and event.get("end_time") is not None
                else None
            ),
            "mudra": event.get("mudra"),
            "knowledge_meaning": event.get("knowledge_meaning"),
            "knowledge_status": event.get("knowledge_status"),
            "verification_status": event.get("verification_status"),
            "claim_id": event.get("claim_id"),
            "source_references": event.get("source_references", []),
            "uncertainty_notes": event.get("uncertainty_notes", []),
            "mudra_confidence": event.get("confidence"),
            "bhava": event.get("bhava"),
            "bhava_confidence": event.get("bhava_confidence"),
            "grounded": True,
            "unresolved": False,
            "semantic_grounding_status": "source_backed_mudra_knowledge",
            "evidence_ids": [grounded_meanings[str(event.get("mudra"))]["evidence_id"]],
        }
        if (
            narrative_events
            and narrative_events[-1]["mudra"] == narrative_event["mudra"]
            and narrative_events[-1]["bhava"] == narrative_event["bhava"]
            and _start_time(narrative_event) <= float(narrative_events[-1]["end_time"] or 0) + 1
        ):
            narrative_events[-1]["end_time"] = narrative_event["end_time"]
            narrative_events[-1]["duration"] = (
                float(narrative_events[-1]["end_time"])
                - float(narrative_events[-1]["start_time"])
            )
        else:
            narrative_events.append(narrative_event)


    # ------------------------------------------------------------------
    # Detected Bhava
    # ------------------------------------------------------------------

    bhava_events: list[dict[str, Any]] = []

    for item in detected:

        if not isinstance(item, dict):
            continue

        label = item.get("label", "")

        if "facial expression" not in label.lower() and "bhava" not in label.lower():
            continue

        bhava_events.append(
            {
                "label": re.sub(r"\s+(?:facial expression|bhava)\s+detected$", "", label, flags=re.IGNORECASE).strip(),
                "observation_type": "predicted_emotion_label",
                "confidence": item.get("confidence"),
                "category": item.get(
                    "category",
                    "detected",
                ),
                "evidence_id": item.get("id"),
            }
        )


    # ------------------------------------------------------------------
    # Clean grounded evidence
    # ------------------------------------------------------------------

    grounded_evidence: list[dict[str, Any]] = []

    for item in grounded:

        if not isinstance(item, dict):
            continue

        label = item.get("label")

        detail = item.get("detail")

        verification_status = item.get("verification_status")
        knowledge_status = item.get("knowledge_status", verification_status)
        source_references = item.get("source_references")
        uncertainty_notes = item.get("uncertainty_notes")
        claim_id = item.get("claim_id")
        if (
            not label
            or not detail
            or verification_status not in {"verified", "partially_verified"}
            or knowledge_status != verification_status
            or not isinstance(claim_id, str)
            or not claim_id.strip()
            or not isinstance(source_references, list)
            or not source_references
            or any(not isinstance(reference, str) or not reference.strip() for reference in source_references)
            or not isinstance(uncertainty_notes, list)
            or any(not isinstance(note, str) for note in uncertainty_notes)
        ):
            continue

        grounded_evidence.append(
            {
                "label": label,
                "meaning": detail,
                "confidence": item.get("confidence"),
                "id": item.get("id"),
                "knowledge_status": knowledge_status,
                "verification_status": verification_status,
                "claim_id": claim_id,
                "source_references": source_references,
                "uncertainty_notes": uncertainty_notes,
            }
        )


    # ------------------------------------------------------------------
    # Clean unresolved evidence
    # ------------------------------------------------------------------

    unresolved_evidence: list[dict[str, Any]] = []

    for item in unresolved:

        if isinstance(item, dict):

            unresolved_evidence.append(
                {
                    "label": item.get("label"),
                    "confidence": item.get("confidence"),
                    "id": item.get("id"),
                }
            )

        else:

            unresolved_evidence.append(
                {
                    "label": str(item),
                    "confidence": None,
                    "id": None,
                }
            )


    # ------------------------------------------------------------------
    # Return package
    # ------------------------------------------------------------------

    return {
        "video_id": (
            fusion.get("analysis_id")
            or fusion.get("video_id")
        ),

        "performance": {
            "duration_seconds": summary.get(
                "duration_seconds"
            ),
            "audio_available": False,
            "lyrics_available": False,
        },

        "temporal_events": temporal_events,

        "narrative_events": narrative_events,

        "bhava_events": bhava_events,

        "grounded_evidence": grounded_evidence,

        "unresolved_evidence": unresolved_evidence,

        "summary": summary,

        "lyrics": None,

        "audio": None,

        "language": None,

        "narrative_confidence": (
            "high"
            if narrative_events
            and any(
                event.get("semantic_grounding_status") == "verified_narrative_context"
                for event in narrative_events
            )
            else "medium"
            if narrative_events
            else "low"
        ),

        "evidence_coverage": {
            "grounded_events": len(narrative_events),
            "grounded_meanings": len(grounded_evidence),
            "unresolved_events_excluded": len(unresolved_evidence),
            "unsupported_narrative_context": True,
        },
    }


# ============================================================================
# VALID EVIDENCE
# ============================================================================

def _has_valid_evidence(evidence: dict) -> bool:
    """Return True when usable evidence exists."""

    grounded = evidence.get(
        "grounded",
        [],
    ) or []

    detected = evidence.get(
        "detected",
        [],
    ) or []

    reliable_grounded = any(
        isinstance(item, dict)
        and item.get("verification_status") in {"verified", "partially_verified"}
        and item.get("knowledge_status") == item.get("verification_status")
        and item.get("claim_id")
        and isinstance(item.get("source_references"), list)
        and item["source_references"]
        and all(isinstance(reference, str) and reference.strip() for reference in item["source_references"])
        for item in grounded
    )
    return reliable_grounded or bool(detected)


# ============================================================================
# TRACEABLE INTERPRETATIONS
# ============================================================================

def _build_interpretations(
    evidence: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[str],
]:

    interpretations: list[dict[str, Any]] = []

    supporting_ids: list[str] = []

    unresolved_ids: list[str] = []


    # ------------------------------------------------------------------
    # Grounded Mudras
    # ------------------------------------------------------------------

    for item in evidence.get(
        "grounded",
        [],
    ):

        if not isinstance(item, dict):
            continue

        label = item.get("label")

        detail = item.get("detail")

        evidence_id = item.get("id")

        verification_status = item.get("verification_status")
        knowledge_status = item.get("knowledge_status")
        claim_id = item.get("claim_id")
        source_references = item.get("source_references")
        uncertainty_notes = item.get("uncertainty_notes")
        if (
            not label
            or not detail
            or not evidence_id
            or verification_status not in {"verified", "partially_verified"}
            or knowledge_status != verification_status
            or not isinstance(claim_id, str)
            or not claim_id.strip()
            or not isinstance(source_references, list)
            or not source_references
            or any(not isinstance(reference, str) or not reference.strip() for reference in source_references)
            or not isinstance(uncertainty_notes, list)
            or any(not isinstance(note, str) for note in uncertainty_notes)
        ):
            continue

        status_text = verification_status.replace("_", " ")
        interpretations.append(
            {
                "id": f"interp-{label.lower()}",
                "statement": (
                    f"The {label} gesture appears in "
                    f"this performance. The knowledge base records "
                    f"a {status_text} meaning for {label}: {detail}."
                ),
                "supporting_evidence": [
                    evidence_id
                ],
                "confidence": item.get(
                    "confidence"
                ),
                "status": "evidence_supported",
                "knowledge_status": knowledge_status,
                "verification_status": verification_status,
                "claim_id": claim_id,
                "source_references": source_references,
                "uncertainty_notes": uncertainty_notes,
            }
        )

        supporting_ids.append(evidence_id)


    # ------------------------------------------------------------------
    # Detected Bhava
    # ------------------------------------------------------------------

    for item in evidence.get(
        "detected",
        [],
    ):

        if not isinstance(item, dict):
            continue

        label = item.get("label")

        evidence_id = item.get("id")

        if not label or not evidence_id:
            continue

        if "bhava" not in label.lower() and "facial expression" not in label.lower():
            continue

        statement_label = re.sub(
            r"\s+(?:facial expression|bhava)\s+detected$",
            "",
            label,
            flags=re.IGNORECASE,
        ).strip()

        interpretations.append(
            {
                "id": f"interp-{evidence_id.lower()}",
                "statement": (
                    f"A facial-expression model recorded the predicted emotion label "
                    f"{statement_label}."
                ),
                "supporting_evidence": [
                    evidence_id
                ],
                "confidence": item.get(
                    "confidence"
                ),
                "status": "evidence_supported",
            }
        )

        supporting_ids.append(evidence_id)


    # ------------------------------------------------------------------
    # Unresolved
    # ------------------------------------------------------------------

    for item in evidence.get(
        "unresolved",
        [],
    ):

        if not isinstance(item, dict):
            continue

        evidence_id = item.get("id")

        if evidence_id:
            unresolved_ids.append(
                evidence_id
            )


    return (
        interpretations,
        supporting_ids,
        unresolved_ids,
    )


# ============================================================================
# FALLBACK
# ============================================================================

def _fallback_story_text(
    response: dict[str, Any],
    code: str,
) -> str:
    """Create a transparent evidence-only fallback story.

    The fallback must never invent unsupported plot details or stale template
    sections. It should only restate the grounded/detected evidence in plain
    prose.
    """

    interpretations = response.get("interpretations", [])

    if not interpretations:
        return _insufficient_story(code)

    if code == "ta":
        lines = [
            "இந்த நடனத்தின் காட்சிப்படுத்தப்பட்ட "
            "சைகைகள் மற்றும் உணர்ச்சி வெளிப்பாடுகளின் "
            "அடிப்படையில் இந்த விளக்கம் உருவாக்கப்பட்டுள்ளது."
        ]
    elif code == "hi":
        lines = [
            "यह व्याख्या नृत्य में दिखाई देने वाले "
            "संकेतों और मॉडल द्वारा दर्ज चेहरे के भावों "
            "पर आधारित है।"
        ]
    elif code == "ml":
        lines = [
            "ഈ വ്യാഖ്യാനം നൃത്തത്തിൽ കണ്ടെത്തിയ "
            "ആംഗ്യങ്ങളും മോഡൽ രേഖപ്പെടുത്തിയ മുഖഭാവ നിരീക്ഷണങ്ങളും "
            "അടിസ്ഥാനമാക്കിയുള്ളതാണ്."
        ]
    else:
        lines = [
            "The dance unfolds through the gestures "
            "and facial-expression observations recorded in the "
            "performance."
        ]

    for interp in interpretations:
        statement = interp.get("statement")
        if statement:
            lines.append(statement)

    if response.get("unresolved_evidence"):
        if code == "ta":
            lines.append(
                "சில சைகைகளுக்கு நம்பகமான "
                "அறிவுத் தளத்தில் பொருள் கிடைக்கவில்லை; "
                "அவற்றின் பொருள் ஊகிக்கப்படவில்லை."
            )
        elif code == "hi":
            lines.append(
                "कुछ संकेतों के लिए विश्वसनीय ज्ञान-आधार "
                "में अर्थ उपलब्ध नहीं था; इसलिए उनका "
                "अर्थ अनुमानित नहीं किया गया।"
            )
        elif code == "ml":
            lines.append(
                "ചില ആംഗ്യങ്ങൾക്ക് വിശ്വസനീയമായ "
                "വിജ്ഞാന-അടിത്തറയിൽ അർത്ഥം ലഭ്യമല്ലാത്തതിനാൽ "
                "അവയുടെ അർത്ഥം അനുമാനിച്ചിട്ടില്ല."
            )
        else:
            lines.append(
                "Some gestures could not be interpreted "
                "because no reliable knowledge-base meaning was available."
            )

    return "\n\n".join(lines)


# ============================================================================
# MAIN STORY GENERATION
# ============================================================================

def generate_story(
    video_id: str,
    language: str = "en",
    provider: str | None = None,
) -> dict[str, Any]:
    """Generate a human-readable story for one video."""

    code = _normalize_language(
        language
    )

    # This retained compatibility helper is not mounted by the production
    # Story route.  Keep its direct callers from bypassing the Gemini-only
    # production policy while the legacy tests continue to use fake providers.
    if settings.app_env.lower() == "production" and provider not in (None, "gemini"):
        raise AppError(
            "Production Story generation requires Gemini.",
            400,
            "PRODUCTION_GEMINI_REQUIRED",
        )


    # ------------------------------------------------------------------
    # Get ONLY this video's fusion result.
    # ------------------------------------------------------------------

    try:

        fusion = get_modality_result(
            video_id,
            "fusion",
        )

    except AppError as exc:

        if exc.code == (
            "MODALITY_RESULT_NOT_FOUND"
        ):

            raise AppError(
                "Fusion result was not found "
                "for this video. Run the fusion "
                "analysis first.",
                404,
                "FUSION_RESULT_REQUIRED",
            ) from exc

        raise

    fusion_analysis_id = fusion.get("analysis_id")
    fusion_video_id = fusion.get("video_id")
    if fusion_analysis_id != video_id or fusion_video_id != video_id:
        raise AppError(
            "Fusion result does not belong to the requested analysis.",
            409,
            "ANALYSIS_ID_MISMATCH",
        )

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    evidence = fusion.get(
        "evidence",
        {},
    ) or {}


    (
        interpretations,
        supporting_ids,
        unresolved_ids,
    ) = _build_interpretations(
        evidence
    )


    response: dict[str, Any] = {

        "analysis_id": video_id,

        "status": (
            "completed"
            if _has_valid_evidence(
                evidence
            )
            else "insufficient_grounded_evidence"
        ),

        "language": code,

        "title": None,

        "story": None,

        "interpretations": interpretations,

        "supporting_evidence": supporting_ids,

        "unresolved_evidence": unresolved_ids,

        "message": None,
    }


    # ------------------------------------------------------------------
    # No evidence
    # ------------------------------------------------------------------

    if not _has_valid_evidence(
        evidence
    ):

        response["message"] = (
            _insufficient_message(code)
        )

        # Leave title and story unset so the UI can present a clear
        # "interpretation unavailable" state instead of a stale default narrative.
        response["title"] = None
        response["story"] = None

        save_modality_result(
            video_id,
            "story",
            response,
        )

        return response


    # ------------------------------------------------------------------
    # Build temporal evidence package
    # ------------------------------------------------------------------

    evidence_package = (
        _build_evidence_package(
            fusion
        )
    )

    evidence_package["language"] = code
    response["narrative_confidence"] = evidence_package["narrative_confidence"]
    response["evidence_coverage"] = evidence_package["evidence_coverage"]


    # ------------------------------------------------------------------
    # Select LLM provider
    # ------------------------------------------------------------------

    try:

        llm_provider = get_provider(
            provider
        )

    except ValueError as exc:

        raise AppError(
            str(exc),
            400,
            "UNKNOWN_PROVIDER",
        ) from exc


    # ------------------------------------------------------------------
    # Provider unavailable
    # ------------------------------------------------------------------

    if not llm_provider.is_available():
        logger.warning(
            "Configured LLM provider unavailable: provider=%s video_id=%s",
            llm_provider.name,
            video_id,
        )
        response["status"] = "generation_failed"
        response["title"] = None
        response["story"] = None
        response["message"] = (
            "Story generation failed: the configured provider was unavailable. "
            "No default narrative was returned."
        )
        response["provider"] = llm_provider.name
        response["model"] = getattr(llm_provider, "_model_name", None)
        response["generation_method"] = "generation_error"

        save_modality_result(video_id, "story", response)
        return response

    result = llm_provider.generate_story(
        evidence_package,
        code,
    )

    if result.error or not result.text:

        logger.warning(
            "LLM story generation failed: "
            "provider=%s model=%s "
            "video_id=%s error_type=%s",
            result.provider,
            result.model,
            video_id,
            type(result.error).__name__
            if result.error
            else "unknown",
        )

        response["status"] = "generation_failed"
        response["title"] = None
        response["story"] = None
        response["message"] = (
            "Story generation failed: "
            f"{result.error or 'The provider returned no usable text.'}"
        )
        response["provider"] = result.provider
        response["model"] = result.model
        response["generation_method"] = "generation_error"

        save_modality_result(video_id, "story", response)
        return response

    response["title"] = _story_title(code)
    final_story = _sanitize_story_text(result.text.strip())
    if (
        _story_violates_evidence(final_story, evidence)
        or _story_omits_grounded_evidence(final_story, evidence)
    ):
        logger.warning(
            "Story contradicted evidence package for video_id=%s. Replacing with deterministic story.",
            video_id,
        )
        final_story = _deterministic_story_from_evidence(evidence_package, code)
    response["story"] = final_story
    response["provider"] = result.provider
    response["model"] = result.model
    response["generation_method"] = "llm"

    save_modality_result(video_id, "story", response)
    return response


# ============================================================================
# TITLES
# ============================================================================

def _story_title(code: str) -> str:
    """Return a neutral title that does not repeat the stale template."""

    return "Bharatanatyam performance interpretation"


def _story_bhava_label(evidence: dict[str, Any]) -> str | None:
    """Return the dominant detected Bhava label from the evidence package."""

    detected_items = evidence.get("detected", []) or evidence.get("bhava_events", []) or []
    for item in detected_items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("bhava") or "").strip()
        if not label:
            continue
        if "bhava" in label.lower() or "facial expression" in label.lower():
            return label
    return None


def _story_bhava_name(evidence: dict[str, Any]) -> str | None:
    """Return the Bhava name without evidence-label suffixes."""

    label = _story_bhava_label(evidence)
    if not label:
        return None

    name = re.sub(r"\s+(?:bhava|facial expression)\s+detected$", "", label, flags=re.IGNORECASE)
    name = re.sub(r"\s+detected$", "", name, flags=re.IGNORECASE)
    return name.strip()


def _deterministic_story_from_evidence(
    evidence: dict[str, Any],
    code: str,
) -> str:
    """Construct a factual story purely from the structured evidence."""

    lines: list[str] = []

    detected_emotion = _story_bhava_name(evidence)
    if detected_emotion:
        lines.append(f"A facial-expression model recorded the predicted emotion label {detected_emotion}.")

    grounded_items = evidence.get("grounded", []) or evidence.get("grounded_evidence", []) or []
    narrative_events = evidence.get("narrative_events", []) or []
    if narrative_events:
        descriptions = [
            f"{event['mudra']}, listed with a {event['verification_status'].replace('_', ' ')} "
            f"knowledge-base meaning of {event['knowledge_meaning'].lower()}"
            for event in narrative_events
            if event.get("mudra") and event.get("knowledge_meaning")
        ]
    else:
        descriptions = [
            f"{item.get('label')}, listed with a {item.get('verification_status', '').replace('_', ' ')} "
            f"knowledge-base meaning of {(item.get('detail') or item.get('meaning')).lower()}"
            for item in grounded_items
            if isinstance(item, dict)
            and item.get("label")
            and (item.get("detail") or item.get("meaning"))
            and item.get("verification_status") in {"verified", "partially_verified"}
            and item.get("knowledge_status") == item.get("verification_status")
            and item.get("claim_id")
            and item.get("source_references")
        ]
    if descriptions:
        if len(descriptions) == 1:
            lines.append(f"The sequence includes {descriptions[0]}.")
        elif len(descriptions) == 2:
            lines.append(f"The sequence begins with {descriptions[0]}, followed by {descriptions[1]}.")
        else:
            first_transition = f"The sequence begins with {descriptions[0]}, followed by {descriptions[1]}."
            remaining = ", ".join(descriptions[2:-1])
            if remaining:
                remaining += ", and "
            else:
                remaining = ""
            lines.append(first_transition)
            lines.append(f"It then continues through {remaining}{descriptions[-1]}.")

    if evidence.get("unresolved") or evidence.get("unresolved_evidence"):
        lines.append(
            "Several other detected gestures remain unresolved because their meanings "
            "are not available in the current knowledge base."
        )

    if not lines:
        return _insufficient_story(code)

    return " ".join(lines)


def _story_omits_grounded_evidence(text: str, evidence: dict[str, Any]) -> bool:
    """Return True when generated prose omits any verified fact."""

    lowered = text.lower()
    for item in evidence.get("grounded", []) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().lower()
        detail = str(item.get("detail", "")).strip().lower()
        if (label and label not in lowered) or (detail and detail not in lowered):
            return True
    return False


def _story_violates_evidence(text: str, evidence: dict[str, Any]) -> bool:
    """Return True when the story contradicts the evidence package."""

    if not text:
        return True

    lowered = text.lower()
    unsupported_phrases = [
        "audience",
        "watched",
        "watching",
        "sorrow",
        "sad",
        "melancholy",
        "longing",
        "pain",
        "suffering",
        "farewell",
        "smile",
        "smiling",
        "eyes",
        "facial expression",
        "mythology",
        "god",
        "gods",
        "krishna",
        "radha",
        "temple",
        "forest",
        "character",
        "characters",
        "relationship",
        "relationships",
        "entered the stage",
        "left the stage",
        "dancer enters",
        "dancer leaves",
        "offers a lotus",
        "melody",
        "music",
        "lyrics",
        "atmosphere",
        "symbolism",
    ]

    if any(phrase in lowered for phrase in unsupported_phrases):
        return True

    detected_bhava = _story_bhava_name(evidence)
    if detected_bhava:
        normalized = detected_bhava.lower().strip()
        forbidden_bhava_words = {
            "angry",
            "sad",
            "happy",
            "fear",
            "disgust",
            "surprise",
            "neutral",
            "joy",
            "love",
        }
        forbidden_bhava_words -= {normalized}
        for word in forbidden_bhava_words:
            if word in lowered and word != normalized:
                return True

    for item in evidence.get("grounded", []) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if label and label.lower() in lowered:
            continue
        if detail and detail.lower() in lowered:
            continue

    unresolved_labels = []
    for item in evidence.get("unresolved", []) or []:
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip()
            if label:
                unresolved_labels.append(label.lower())
        else:
            label = str(item).strip()
            if label:
                unresolved_labels.append(label.lower())
    for label in unresolved_labels:
        if label in lowered:
            return True

    return False


def _sanitize_story_text(text: str) -> str:
    """Strip stale template language and section headings from generated prose."""

    if not text:
        return text

    cleaned = text.strip()

    stale_markers = [
        "Evidence-Grounded Interpretation",
        "The Story Within the Dance",
        "Sad Bhava",
        "Angry Bhava",
        "Title:",
        "Opening paragraph:",
        "Development paragraph:",
        "Emotional paragraph:",
        "Closing paragraph:",
        "The performance begins",
        "The dancer's movements",
        "audience",
    ]

    for marker in stale_markers:
        cleaned = cleaned.replace(marker, "")

    cleaned = re.sub(
        r"(?im)^\s*(Title|Opening paragraph|Development paragraph|Emotional paragraph|Closing paragraph)\s*[:\-]?\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -:;\n\t")

    return cleaned


# ============================================================================
# NO-EVIDENCE MESSAGES
# ============================================================================

def _insufficient_message(
    code: str,
) -> str:

    if code == "ta":

        return (
            "நம்பகமான சான்றுகள் இல்லாததால் "
            "நம்பகமான கதையை உருவாக்க முடியவில்லை."
        )

    if code == "hi":

        return (
            "विश्वसनीय साक्ष्य उपलब्ध नहीं होने के कारण "
            "विश्वसनीय कहानी उत्पन्न नहीं की जा सकी।"
        )

    if code == "ml":

        return (
            "വിശ്വസനീയമായ തെളിവുകൾ ലഭ്യമല്ലാത്തതിനാൽ "
            "വിശ്വസനീയമായ കഥ സൃഷ്ടിക്കാൻ കഴിഞ്ഞില്ല."
        )

    return (
        "A reliable story cannot be generated because "
        "no usable reliable evidence is available."
    )


def _insufficient_story(
    code: str,
) -> str:

    if code == "ta":

        return (
            "இந்த நடனத்திலிருந்து நம்பகமான கதையை "
            "உருவாக்க போதுமான நம்பகமான "
            "சான்றுகள் கிடைக்கவில்லை."
        )

    if code == "hi":

        return (
            "इस नृत्य से विश्वसनीय कहानी बनाने के लिए "
            "पर्याप्त विश्वसनीय साक्ष्य उपलब्ध नहीं हैं।"
        )

    if code == "ml":

        return (
            "ഈ നൃത്തത്തിൽ നിന്ന് വിശ്വസനീയമായ ഒരു കഥ "
            "സൃഷ്ടിക്കാൻ ആവശ്യമായ വിശ്വസനീയമായ തെളിവുകൾ "
            "ലഭ്യമല്ല."
        )

    return (
        "There is not enough reliable evidence in this "
        "performance to create a reliable story."
    )
