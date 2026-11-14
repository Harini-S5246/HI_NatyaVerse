"""Final provider-neutral, package-only narration layer.

It neither reads analysis records nor calls model/fusion services. The sole
factual input is a validated performance interpretation package.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from app.config import settings
from app.services.llm import LLMProvider, StructuredGenerationRequest, get_provider
from app.services.llm.base import STORY_OUTPUT_JSON_SCHEMA
from app.services.performance_interpretation_service import (
    PerformanceInterpretationValidationError,
    validate_performance_interpretation,
)

SCHEMA_VERSION = "1.0.0"
_MAX_PROMPT_CHARS = 60_000
_STORY_MAX_OUTPUT_TOKENS = 8192
STORY_PRESENTATION_VERSION = "38"
_OUTPUT_LANGUAGES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "ml": "Malayalam",
    "te": "Telugu",
    "kn": "Kannada",
    "bn": "Bengali",
}
_LANGUAGE_SCRIPT_RANGES = {
    "ta": (0x0B80, 0x0BFF),
    "hi": (0x0900, 0x097F),
    "ml": (0x0D00, 0x0D7F),
    "te": (0x0C00, 0x0C7F),
    "kn": (0x0C80, 0x0CFF),
    "bn": (0x0980, 0x09FF),
}
_BHAVA_STORY_MEANINGS = {
    "angry": "anger",
    "sad": "sorrow",
    "surprise": "surprise",
    "happy": "joy",
    "disgust": "aversion",
}
logger = logging.getLogger(__name__)
_FORBIDDEN_PURE_DANCE_TERMS = {
    "krishna", "radha", "shiva", "devi", "character", "characters",
    "mythology", "forest", "temple", "because", "therefore", "caused",
    "relationship", "relationships", "dialogue", "lyrics", "choreography",
    "facial expression", "movement", "enters", "leaves",
}


class NarrativeGenerationValidationError(ValueError):
    """Raised for unsupported package input or LLM output."""


class NarrativeGenerationRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int | None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Gemini is temporarily rate limited.")


class NarrativeGenerationProviderError(RuntimeError):
    def __init__(self, error_code: str, error_type: str) -> None:
        self.error_code = error_code
        self.error_type = error_type
        super().__init__(error_type)


def configured_provider_metadata() -> tuple[LLMProvider, str, str]:
    """Resolve the backend-selected provider without any fallback.

    Production deliberately permits Gemini only. Other registered adapters
    remain usable through explicit non-production/test configuration.
    """
    provider_name = settings.story_llm_provider
    if getattr(settings, "app_env", "development").lower() == "production" and provider_name != "gemini":
        raise NarrativeGenerationValidationError("Production Story generation requires STORY_LLM_PROVIDER=gemini.")
    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        raise NarrativeGenerationValidationError(f"Configured story provider is invalid: {exc}") from exc
    return provider, provider.name, provider.model


def _blocked(package: dict[str, Any], status: str, message: str, provider_name: str, model: str, *, language: str = "en", retry_after_seconds: int | None = None, error_code: str | None = None) -> dict[str, Any]:
    response = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": package["analysis_id"], "video_id": package["video_id"],
        "mode": package["performance_mode"]["label"], "status": status,
        "language": language,
        "title": None, "narrative": None, "evidence_coverage": 0.0,
        "used_event_ids": [], "limitations": list(package.get("limitations", [])),
        "provider": provider_name, "model": model, "message": message,
    }
    if retry_after_seconds is not None:
        response["retry_after_seconds"] = retry_after_seconds
    if error_code is not None:
        response["error_code"] = error_code
    return response


def _validate_package(package: Any) -> dict[str, Any]:
    try:
        validated = validate_performance_interpretation(package, for_production=True)
    except PerformanceInterpretationValidationError as exc:
        raise NarrativeGenerationValidationError(str(exc)) from exc
    required = {"analysis_id", "video_id", "performance_mode", "interpretation_status", "events", "limitations"}
    if not isinstance(validated, dict) or not required.issubset(validated):
        raise NarrativeGenerationValidationError("Performance Interpretation Package is incomplete.")
    if validated["analysis_id"] != validated["video_id"]:
        raise NarrativeGenerationValidationError("analysis_id and video_id must match.")
    return validated


def _eligible_events(package: dict[str, Any]) -> list[dict[str, Any]]:
    mode = package["performance_mode"]["label"]
    events = package["events"]
    if mode in {"pure_dance", "evidence_based"}:
        return [event for event in events if event["type"] != "verified_narrative_event"]
    return [event for event in events if event["type"] == "verified_narrative_event"]


def normalize_output_language(language: str) -> tuple[str, str]:
    normalized = language.strip().lower()
    for code, name in _OUTPUT_LANGUAGES.items():
        if normalized in {code, name.lower()}:
            return code, name
    raise NarrativeGenerationValidationError(f"Unsupported story language: {language}.")


def _observed_mudra_names(events: list[dict[str, Any]]) -> set[str]:
    names: set[str] = {"Bharatanatyam"}

    def add_label(value: Any) -> None:
        if isinstance(value, str) and len(value.split()) <= 3:
            names.update(re.findall(r"[A-Za-z][A-Za-z'-]*", value))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = re.sub(r"[^a-z]", "", key.lower())
                if normalized_key in {"mudra", "mudralabel", "mudraname", "observedmudra", "detectedmudra"}:
                    if isinstance(item, str):
                        add_label(item)
                    elif isinstance(item, dict):
                        for label_key in ("name", "label", "value", "prediction", "detected", "observed"):
                            add_label(item.get(label_key))
                        visit(item)
                    else:
                        visit(item)
                elif normalized_key in {"name", "label", "value", "prediction", "detected", "observed"}:
                    continue
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for event in events:
        visit(event.get("observations", {}))
    return names


def _validate_output_language(
    title: str,
    narrative: str,
    language: str,
    mode: str,
    allowed_names: set[str] | None = None,
) -> None:
    script_range = _LANGUAGE_SCRIPT_RANGES.get(language)
    if mode != "evidence_based" or script_range is None:
        return
    start, end = script_range
    paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", narrative.strip()) if paragraph.strip()]
    all_text = [title, *paragraphs]
    if any(sum(start <= ord(character) <= end for character in text) < 5 for text in all_text):
        raise NarrativeGenerationValidationError(
            f"The generated title and every narrative paragraph must be written in {_OUTPUT_LANGUAGES[language]} script."
        )
    allowed = {name.casefold() for name in (allowed_names or set())}
    latin_words = re.findall(r"[A-Za-z][A-Za-z'-]*", f"{title}\n{narrative}")
    if any(word.casefold() not in allowed for word in latin_words):
        raise NarrativeGenerationValidationError(
            f"The generated title and narrative contain untranslated English text for {_OUTPUT_LANGUAGES[language]}."
        )


def _validate_human_facing_narrative(
    title: str,
    narrative: str,
    mode: str,
    minimum_paragraphs: int = 3,
) -> None:
    if mode != "evidence_based":
        return
    paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", narrative.strip()) if paragraph.strip()]
    if not minimum_paragraphs <= len(paragraphs) <= 12:
        raise NarrativeGenerationValidationError(
            f"Evidence-based stories must contain {minimum_paragraphs}-12 natural narrative paragraphs."
        )

    technical_patterns = (
        (r"\b(?:the\s+model|model)\s+(?:detected|predicts|classified|identified|observed|reported)\b", "model wording"),
        (r"\bmodel\s+observations?\b", "model observation wording"),
        (r"\b(?:detected|predicted)\s+(?:mudra|bhava|gesture|pose|expression|label|symbol)\b", "technical detection wording"),
        (r"\b(?:expression|mudra|bhava|gesture|pose|symbol|label)\s+labels?\b", "technical label wording"),
        (r"\b(?:mudra|bhava|gesture|pose|expression|symbol|label)\b(?:[^.!?]{0,80})?\b(?:associated with|classified as|identified as|denotes|indicates|symbolizes|represents|means)\b", "technical definition wording"),
        (r"\b[A-Z][A-Za-z'-]*\s+(?:associated with|classified as|identified as|denotes|indicates|symbolizes|represents|means)\b", "technical label definition"),
        (r"\b(?:frame|timestamp|event id|analysis id|video id|source reference|provenance|confidence|probability|coverage|artifact|model name)\b", "technical metadata"),
        (r"\b(?:frame)\s+\d+\b", "frame number"),
        (r"\b(?:confidence|probability)\s*[:=]?\s*(?:0|[0-9]*\.[0-9]+)", "confidence score"),
        (r"\b(?:analysis|evidence|performance)\s+(?:segment|coverage|interpretation|progression|summary)\b", "technical report wording"),
    )
    combined_text = f"{title}\n{narrative}"
    technical_terms = []
    seen = set()
    for pattern, label in technical_patterns:
        if re.search(pattern, combined_text, flags=re.IGNORECASE):
            if label not in seen:
                technical_terms.append(label)
                seen.add(label)
    if technical_terms:
        raise NarrativeGenerationValidationError(
            "Evidence-based stories must use human-facing narrative language. "
            f"Technical wording found: {', '.join(technical_terms)}."
        )
    roadmap_patterns = (
        r"\b(?:phase|segment|section|stage)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        r"\b(?:sequence|timeline)\b",
    )
    if any(re.search(pattern, narrative, flags=re.IGNORECASE) for pattern in roadmap_patterns):
        raise NarrativeGenerationValidationError(
            "Evidence-based stories must express chronology naturally without phase labels or report language."
        )
    if re.search(r"\bexpressive\s+journey\b", title, flags=re.IGNORECASE):
        raise NarrativeGenerationValidationError(
            "Evidence-based story titles must describe this story's specific supported turn, not generic expression."
        )
    title_terms = (
        "progression",
        "performance",
        "interpretation",
        "analysis",
        "evidence",
        "model",
    )
    title_lower = title.casefold()
    technical_title_terms = [
        term for term in title_terms
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", title_lower)
    ]
    if technical_title_terms:
        raise NarrativeGenerationValidationError(
            "Evidence-based story titles must be evocative rather than technical. "
            f"Technical wording found: {', '.join(technical_title_terms)}."
        )


def _ensure_narrative_paragraphs(
    narrative: str,
    mode: str,
    minimum_paragraphs: int = 3,
) -> str:
    if mode != "evidence_based":
        return narrative
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", narrative.strip()) if paragraph.strip()]
    if 3 <= len(paragraphs) <= 12:
        return "\n\n".join(paragraphs)
    sentences = [
        sentence.strip()
        for paragraph in paragraphs
        for sentence in re.split(r"(?<=[.!?।])\s+", paragraph)
        if sentence.strip()
    ]
    if len(sentences) < minimum_paragraphs:
        raise NarrativeGenerationValidationError(
            f"Evidence-based stories need at least {minimum_paragraphs} complete sentences for readable paragraph formatting."
        )
    paragraph_count = min(12, max(minimum_paragraphs, min(4, len(sentences))))
    base_size, remainder = divmod(len(sentences), paragraph_count)
    formatted = []
    offset = 0
    for index in range(paragraph_count):
        size = base_size + (1 if index < remainder else 0)
        formatted.append(" ".join(sentences[offset:offset + size]))
        offset += size
    return "\n\n".join(formatted)


def _evidence_based_story_evidence(eligible_events: list[dict[str, Any]]) -> dict[str, Any]:
    if not eligible_events:
        return {
            "chronological_beats": [],
            "supported_pose_context_available": False,
        }

    timed_events: list[tuple[float, float, int, dict[str, Any]]] = []
    for index, event in enumerate(eligible_events):
        start = event.get("start_time")
        end = event.get("end_time")
        if isinstance(start, (int, float)) and not isinstance(start, bool):
            start_value = float(start)
            end_value = (
                float(end)
                if isinstance(end, (int, float)) and not isinstance(end, bool)
                else start_value
            )
            timed_events.append((start_value, end_value, index, event))
    if len(timed_events) == len(eligible_events):
        ordered_events = [item[3] for item in sorted(timed_events, key=lambda item: (item[0], item[2]))]
        timeline_start = min(item[0] for item in timed_events)
        timeline_end = max(item[1] for item in timed_events)
        duration = max(0.0, timeline_end - timeline_start)
        segment_count = max(1, min(15, int((duration + 27.999) // 28)))
        if duration:
            event_segments: list[list[dict[str, Any]]] = [[] for _ in range(segment_count)]
            for start, _, _, event in sorted(timed_events, key=lambda item: (item[0], item[2])):
                segment_index = min(segment_count - 1, int((start - timeline_start) / duration * segment_count))
                event_segments[segment_index].append(event)
            event_segments = [segment for segment in event_segments if segment]
        else:
            event_segments = [ordered_events]
    else:
        ordered_events = eligible_events
        segment_count = max(1, min(15, (len(ordered_events) + 19) // 20))
        event_segments = [
            ordered_events[index * len(ordered_events) // segment_count:(index + 1) * len(ordered_events) // segment_count]
            for index in range(segment_count)
        ]

    def pattern_summaries(
        entries: list[tuple[str, Any, dict[str, Any] | None]],
        *,
        limit: int,
    ) -> list[dict[str, str]]:
        patterns: dict[str, dict[str, Any]] = {}
        for order, (meaning, confidence, knowledge) in enumerate(entries):
            pattern = patterns.setdefault(
                meaning,
                {"count": 0, "confidence": 0.0, "first": order, "knowledge": []},
            )
            pattern["count"] += 1
            pattern["confidence"] += float(confidence)
            if knowledge is not None:
                pattern["knowledge"].append(knowledge)
        selected = sorted(
            patterns.items(),
            key=lambda item: (-int(item[1]["count"]), int(item[1]["first"])),
        )[:limit]
        selected.sort(key=lambda item: int(item[1]["first"]))
        return [
            {
                "meaning": meaning,
                **({
                    "recognition_confidence": float(details["confidence"]) / int(details["count"]),
                    "verification_status": (
                        "partially_verified"
                        if any(item["verification_status"] == "partially_verified" for item in details["knowledge"])
                        else "verified"
                    ),
                    "knowledge_status": (
                        "partially_verified"
                        if any(item["knowledge_status"] == "partially_verified" for item in details["knowledge"])
                        else "verified"
                    ),
                    "claim_ids": list(dict.fromkeys(item["claim_id"] for item in details["knowledge"])),
                    "source_references": list(dict.fromkeys(
                        reference
                        for item in details["knowledge"]
                        for reference in item["source_references"]
                    )),
                    "uncertainty_notes": list(dict.fromkeys(
                        note
                        for item in details["knowledge"]
                        for note in item["uncertainty_notes"]
                    )),
                } if details["knowledge"] else {
                    "certainty": (
                    "tentative"
                    if float(details["confidence"]) / int(details["count"]) < 0.5
                    else "more supported"
                    ),
                }),
                "recurrence": "recurring" if int(details["count"]) > 1 else "brief",
            }
            for meaning, details in selected
        ]

    segments = []
    previous_expressions: set[str] = set()
    previous_gestures: set[str] = set()
    seen_expressions: set[str] = set()
    seen_gestures: set[str] = set()
    for index, segment_events in enumerate(event_segments):
        expressions: list[tuple[str, Any, dict[str, Any] | None]] = []
        gestures: list[tuple[str, Any, dict[str, Any] | None]] = []
        pose_context: list[str] = []
        for event in segment_events:
            observations = event.get("observations", {})
            if not isinstance(observations, dict):
                continue
            pose = observations.get("pose_context")
            if isinstance(pose, str) and pose.strip() and pose.strip() not in pose_context:
                pose_context.append(pose.strip())
            mudra = observations.get("mudra")
            if (
                isinstance(mudra, dict)
                and mudra.get("verification_status") in {"verified", "partially_verified"}
                and mudra.get("knowledge_status") == mudra.get("verification_status")
                and isinstance(mudra.get("claim_id"), str)
                and mudra["claim_id"].strip()
                and isinstance(mudra.get("source_references"), list)
                and mudra["source_references"]
                and all(isinstance(reference, str) and reference.strip() for reference in mudra["source_references"])
                and isinstance(mudra.get("uncertainty_notes"), list)
                and isinstance(mudra.get("meaning"), str)
                and mudra["meaning"].strip()
            ):
                meaning = re.sub(r"\s*\([^)]*\)", "", mudra["meaning"]).strip(" /,;")
                if meaning:
                    gestures.append((meaning, mudra.get("confidence", 0.0), {
                        "knowledge_status": mudra["knowledge_status"],
                        "verification_status": mudra["verification_status"],
                        "claim_id": mudra["claim_id"],
                        "source_references": mudra["source_references"],
                        "uncertainty_notes": mudra["uncertainty_notes"],
                    }))
            bhava = observations.get("bhava")
            if isinstance(bhava, dict) and isinstance(bhava.get("label"), str):
                expression = _BHAVA_STORY_MEANINGS.get(bhava["label"].casefold())
                if expression:
                    expressions.append((expression, bhava.get("confidence", 0.0), None))
        expressive_qualities = pattern_summaries(expressions, limit=5)
        symbolic_associations = pattern_summaries(gestures, limit=2)
        current_expressions = {item["meaning"] for item in expressive_qualities}
        current_gestures = {item["meaning"] for item in symbolic_associations}
        segment = {
            "event_ids": [event["event_id"] for event in segment_events],
            "expressive_qualities": expressive_qualities,
            "expressive_developments": [
                {
                    "meaning": item["meaning"],
                    "change": "returns" if item["meaning"] in seen_expressions else "emerges",
                }
                for item in expressive_qualities
                if item["meaning"] not in previous_expressions
            ],
            "continuing_qualities": [
                item["meaning"] for item in expressive_qualities
                if item["meaning"] in previous_expressions
            ],
            "symbolic_associations": symbolic_associations,
            "symbolic_developments": [
                {
                    "meaning": item["meaning"],
                    "change": "returns" if item["meaning"] in seen_gestures else "emerges",
                }
                for item in symbolic_associations
                if item["meaning"] not in previous_gestures
            ],
        }
        if pose_context:
            segment["supported_pose_context"] = pose_context
        segments.append(segment)
        seen_expressions.update(current_expressions)
        seen_gestures.update(current_gestures)
        previous_expressions = current_expressions
        previous_gestures = current_gestures

    return {
        "beat_count": len(segments),
        "chronological_beats": segments,
        "supported_pose_context_available": any(segment.get("supported_pose_context") for segment in segments),
    }


def _contains_unresolved_template(value: Any) -> bool:
    if isinstance(value, str):
        return re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", value) is not None
    if isinstance(value, dict):
        return any(_contains_unresolved_template(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unresolved_template(item) for item in value)
    return False


def _prompt(package: dict[str, Any], eligible_events: list[dict[str, Any]], language: str = "en") -> str:
    _, language_name = normalize_output_language(language)
    mode = package["performance_mode"]["label"]
    if mode == "evidence_based":
        if _contains_unresolved_template(eligible_events):
            raise NarrativeGenerationValidationError(
                "Validated evidence contains an unresolved template placeholder."
            )
        evidence = _evidence_based_story_evidence(eligible_events)
    else:
        evidence = {
            "analysis_id": package["analysis_id"],
            "mode": package["performance_mode"],
            "events": eligible_events,
            "limitations": package["limitations"],
        }
        if "audio_context" in package:
            evidence["audio"] = package["audio_context"]

    if mode == "evidence_based":
        instructions = """You are a thoughtful Bharatanatyam storyteller. Turn the validated observations into a human-understandable account of the expressive journey across the complete performance, not a report of what a system detected. Generic predicted emotion labels are facial-expression observations, not classical Bhava or Rasa classifications. The supplied observations are the only source of facts; interpret them cautiously and never turn them into a made-up plot.

Return JSON only with exactly: title (string), narrative (string), used_event_ids (array of strings).

The input is a complete, ordered account of validated moments from the opening to the close. Use all meaningful expressive changes in the input; do not summarize only the most common qualities or skip its middle. Each chronological beat includes all of its event_ids, expressive qualities, and explicit emerging/returning versus continuing qualities. Use those developments to shape the story's turns; do not restate every continuing quality in each paragraph. Symbolic associations come only from knowledge-base meanings that retain verification status and provenance; physical context is included only when supported. Do not infer an order among qualities listed within one beat.

Write 8-12 natural paragraphs when there are at least 8 chronological beats, following the complete development and giving meaningful changes enough space. Prefer one paragraph for each beat; combine adjacent beats only when their evidence repeats without a meaningful change. For fewer beats, let the available evidence determine a shorter structure. Aim for roughly 500-900 English words, or comparable natural detail in the requested language, when the evidence supports that depth; never pad with invented or repeated content. Use enough sentences to explain distinct developments, while making each paragraph add something new. Include an opening, development through the middle, later changes, and a conclusion grounded in the final evidence. Explain an emotional return or coexistence only when shown by the later observations.

Ground every claim in the package. Translate generic predicted emotion labels into cautious human-readable expressive qualities, not classical Bhava/Rasa labels or verified inner emotions; do not expose raw labels or claim what the dancer literally feels. Use model confidence only for the corresponding observation, never as cultural verification. Keep facial-expression observations separate from Mudra knowledge; co-occurrence or temporal overlap does not establish a cultural relationship. A change in expression does not establish its cause. Explain why a feeling changes, or what the performer intends, only when supplied evidence explicitly supports it; otherwise describe the expressive shift without inventing a reason. Do not invent characters, relationships, actions, places, plot, lyrics, dialogue, or mythology. The evolving expression itself can be the complete story.

Use knowledge-base meanings naturally where they add meaning, retaining their supplied verification status and varying them across the performance instead of listing Mudra names or repeating one meaning mechanically. Refer to these as symbolic associations (for example, an association with greeting), never as physical gestures the performer forms, repeats, or performs. A supplied meaning is not evidence of a literal object, action, intention, posture, choreography, or scene. Describe pose or physical context only when explicitly supplied in the input. Do not infer movement, facial action, gaze, sound, or pace.

Use direct, fluent prose for a general audience. The narrator speaks about the unfolding performance itself, never about how the evidence was organized. Natural transitions such as “at first,” “as this develops,” and “by the close” may be used sparingly, not as repeated paragraph templates. Make each paragraph contribute a distinct change or development. Carry a continuing quality as a thread without listing it again in every paragraph; mention only the one or two qualities that matter most in that passage, and avoid stacked qualifiers or formulaic repetition of words like “brief,” “recurring,” “tentative,” and “alongside.” Do not narrate each detection, repeat the same point to reach a word count, or use headings, numbered sections, or lists. Never label a passage as a numbered phase, segment, section, or stage, and never call the passage a sequence or timeline. Avoid abstract report wording such as presentation, expressive range, or motif. Keep technical terms, raw model labels, timestamps, frame numbers, and event identifiers out of the title and narrative. Give the story a specific, natural title naming a supported emotional turn; do not use a generic title such as “An Expressive Journey” or “Contrasting Tones.” Use the same requested language in the title and narrative. End with the latest supported expressive state; do not claim a feeling disappeared if several qualities coexist there. Return every supplied event_id in chronological order only in used_event_ids; identifiers must not appear in the title or narrative."""
        if not evidence["supported_pose_context_available"]:
            instructions += (
                "\n\nNo supported pose or physical context was detected in these observations. Do not describe the performer "
                "forming or performing gestures, moving, or using any body part. Refer only to a supplied "
                "Mudra meaning as an abstract symbolic association, such as “an association with greeting returns.”"
            )
    else:
        instructions = """You are an evidence-grounded Bharatanatyam performance narrator. The supplied validated evidence, including explicit knowledge verification statuses, is the complete source of truth.

Return JSON only with exactly: title (string), narrative (string), used_event_ids (array of strings).
Use only the supplied event statements verbatim, in their supplied order. Add no unsupported characters, mythology, actions, locations, relationships, intentions, causes, consequences, lyrics, dialogue, choreography, movement, facial expressions, or objects. Do not mention event IDs in narrative text.

For pure_dance, write a performance interpretation, not a fictional story. For narrative_dance, use only verified narrative events. Do not add transitions between events."""

    language_instruction = (
        f"REQUESTED OUTPUT LANGUAGE: {language_name}\n"
        f"You are transforming validated Bharatanatyam observations into a story for a normal audience in {language_name}. "
        f"Write the title and the entire narrative entirely in {language_name}. Do not mix English sentences into the narrative. "
        "Translate each emotional concept by its intended meaning, not by a misleading literal dictionary equivalent. If a natural equivalent is uncertain, describe the expressive change neutrally rather than using an incorrect or awkward word. "
        "Keep Bharatanatyam Mudra names in their original form when appropriate, but explain any supplied meaning in the requested language. "
        "For non-English output, every paragraph must use the requested script; do not include Latin-script translations of Mudra meanings or English Bhava labels. Preserve Latin spelling only for Mudra names actually present in the supplied observations; translate all other prose completely. Maintain the same chronological coverage and level of detail as the English version; do not shorten the story because of the requested language. "
        "When a gesture or expression has confidence below 0.5, describe it only as possible or tentative in the requested language; do not state its derived image as a definite title. If no specific image can be titled cautiously, choose a neutral title based on the supported change in expression. "
        "Keep used_event_ids unchanged as identifiers."
    )
    prompt = f"{language_instruction}\n\n{instructions}\n\nEVIDENCE:\n{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}"
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise NarrativeGenerationValidationError(
            f"Validated evidence is too large for one story request ({len(prompt)} characters; limit {_MAX_PROMPT_CHARS})."
        )
    if re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", prompt):
        raise NarrativeGenerationValidationError("Prompt contains an unresolved template placeholder.")
    return prompt


def _invoke_provider(
    provider: LLMProvider,
    prompt: str,
    *,
    video_id: str,
    evidence_items: int,
) -> Any:
    """Invoke one selected provider with the canonical validated request."""
    result = provider.generate(StructuredGenerationRequest(
        prompt=prompt,
        max_tokens=_STORY_MAX_OUTPUT_TOKENS,
        video_id=video_id,
        evidence_items=evidence_items,
        response_schema=STORY_OUTPUT_JSON_SCHEMA,
    ))
    if result.error:
        if result.error_code == "GEMINI_RATE_LIMITED":
            raise NarrativeGenerationRateLimitError(result.retry_after_seconds)
        error_code = result.error_code
        if error_code is None:
            if "API_KEY" in result.error or "SDK is not installed" in result.error:
                error_code = "PROVIDER_NOT_CONFIGURED"
            elif "invalid structured JSON" in result.error:
                error_code = "PROVIDER_INVALID_JSON"
            elif "empty response" in result.error:
                error_code = "PROVIDER_EMPTY_RESPONSE"
            elif "truncated" in result.error:
                error_code = "PROVIDER_OUTPUT_TRUNCATED"
            else:
                error_code = "PROVIDER_REQUEST_FAILED"
        raw_error_type = result.error.partition(":")[0]
        error_type = raw_error_type if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,79}", raw_error_type) else "ProviderError"
        raise NarrativeGenerationProviderError(error_code, error_type)
    # Gemini parses structured output at the transport boundary.  This object
    # still goes through _parse_and_validate_output below, which is the sole
    # provider-independent evidence and shape validator.
    return result.structured_output if result.structured_output is not None else result.text


def _parse_and_validate_output(raw: str | Any, package: dict[str, Any], eligible_events: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    if not raw:
        raise NarrativeGenerationValidationError("The configured provider returned an empty response.")
    if isinstance(raw, dict):
        output = raw
    else:
        try:
            output = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise NarrativeGenerationValidationError("Provider response is not valid structured JSON.") from exc
    if not isinstance(output, dict) or set(output) != {"title", "narrative", "used_event_ids"}:
        raise NarrativeGenerationValidationError("Provider response has an unsupported structure.")
    title, narrative, used_ids = output.get("title"), output.get("narrative"), output.get("used_event_ids")
    if not isinstance(title, str) or not title.strip() or not isinstance(narrative, str) or not narrative.strip() or not isinstance(used_ids, list) or not all(isinstance(item, str) for item in used_ids):
        raise NarrativeGenerationValidationError("Provider response fields are invalid.")
    eligible_by_id = {event["event_id"]: event for event in eligible_events}
    if not used_ids or len(set(used_ids)) != len(used_ids) or any(event_id not in eligible_by_id for event_id in used_ids):
        raise NarrativeGenerationValidationError("Provider response references an unknown or duplicate event ID.")
    ordered_ids = [event["event_id"] for event in eligible_events if event["event_id"] in used_ids]
    if used_ids != ordered_ids:
        raise NarrativeGenerationValidationError("Provider response changed verified event ordering.")
    mode = package["performance_mode"]["label"]
    if mode != "evidence_based":
        required_text = "\n\n".join(eligible_by_id[event_id]["statement"] for event_id in used_ids)
        if narrative.strip() != required_text:
            raise NarrativeGenerationValidationError("Provider narrative adds, omits, or changes supported event statements.")
    if mode == "pure_dance":
        lowered = f"{title} {narrative}".lower()
        if any(term in lowered for term in _FORBIDDEN_PURE_DANCE_TERMS):
            raise NarrativeGenerationValidationError("Pure-dance output contains an unsupported narrative claim.")
    return title.strip(), narrative.strip(), used_ids


def generate_narrative(
    package: Any,
    *,
    language: str = "en",
    invoke: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Narrate one production-eligible package, with no fabricated fallback."""
    provider, provider_name, model = configured_provider_metadata()
    try:
        validated = _validate_package(package)
    except NarrativeGenerationValidationError:
        # Invalid input has no safe analysis identity guarantee, so it is not returned as a generation response.
        raise
    language_code, _ = normalize_output_language(language)
    if validated["performance_mode"]["label"] == "unknown":
        return _blocked(validated, "unavailable", "An evidence-grounded narrative interpretation is unavailable because the performance type has not been verified.", provider_name, model, language=language_code)
    if validated["interpretation_status"] != "available":
        return _blocked(validated, "blocked", "Generation is blocked because no verified interpretation evidence is available.", provider_name, model, language=language_code)
    eligible = _eligible_events(validated)
    if not eligible:
        return _blocked(validated, "blocked", "Generation is blocked because no eligible verified events are available.", provider_name, model, language=language_code)
    try:
        prompt = _prompt(validated, eligible, language_code)
        segment_count = (
            len(_evidence_based_story_evidence(eligible)["chronological_beats"])
            if validated["performance_mode"]["label"] == "evidence_based"
            else len(eligible)
        )
        minimum_paragraphs = 8 if segment_count >= 8 else 3
        logger.info(
            "[STORY] video_id=%s analysis_id=%s evidence_found=True timeline_count=%s narrative_segments=%s prompt_contains_placeholders=False synthetic_fixture=False prompt_chars=%s",
            validated["video_id"],
            validated["analysis_id"],
            len(eligible),
            segment_count,
            len(prompt),
        )
        raw = invoke(prompt) if invoke else _invoke_provider(
            provider,
            prompt,
            video_id=validated["video_id"],
            evidence_items=len(eligible),
        )
        title, narrative, used_ids = _parse_and_validate_output(raw, validated, eligible)
        narrative = _ensure_narrative_paragraphs(
            narrative,
            validated["performance_mode"]["label"],
            minimum_paragraphs,
        )
        _validate_output_language(
            title,
            narrative,
            language_code,
            validated["performance_mode"]["label"],
            _observed_mudra_names(eligible),
        )
        _validate_human_facing_narrative(
            title,
            narrative,
            validated["performance_mode"]["label"],
            minimum_paragraphs,
        )
    except NarrativeGenerationRateLimitError as exc:
        seconds = exc.retry_after_seconds
        suffix = f" Please retry after approximately {seconds} seconds." if seconds else " Please retry shortly."
        return _blocked(validated, "retryable", f"Gemini is temporarily rate limited.{suffix}", provider_name, model, language=language_code, retry_after_seconds=seconds, error_code="GEMINI_RATE_LIMITED")
    except NarrativeGenerationProviderError as exc:
        logger.warning(
            "[STORY] video_id=%s analysis_id=%s provider_request_failed provider=%s error_code=%s error_type=%s",
            validated["video_id"],
            validated["analysis_id"],
            provider_name,
            exc.error_code,
            exc.error_type,
        )
        if exc.error_code in {"GEMINI_TIMEOUT", "GEMINI_CONNECTION_FAILED", "GEMINI_RATE_LIMITED"}:
            if exc.error_code == "GEMINI_TIMEOUT":
                message = "Gemini request timed out. The request was not retried automatically; please retry Generate Story."
            else:
                message = "Gemini is temporarily unavailable. The request was not retried automatically; please retry Generate Story."
            return _blocked(validated, "retryable", message, provider_name, model, language=language_code, error_code=exc.error_code)
        if exc.error_code in {"GEMINI_OUTPUT_TRUNCATED", "PROVIDER_OUTPUT_TRUNCATED"}:
            return _blocked(validated, "blocked", "Gemini reached its output-token limit before completing story JSON. No fallback story was used.", provider_name, model, language=language_code, error_code=exc.error_code)
        if exc.error_code in {"GEMINI_INVALID_JSON", "GEMINI_EMPTY_RESPONSE", "PROVIDER_INVALID_JSON", "PROVIDER_EMPTY_RESPONSE"}:
            return _blocked(validated, "blocked", "The configured provider did not return valid story JSON. No fallback story was used.", provider_name, model, language=language_code, error_code=exc.error_code)
        if exc.error_code == "PROVIDER_NOT_CONFIGURED":
            credential_name = f"{provider_name.upper()}_API_KEY"
            return _blocked(
                validated,
                "blocked",
                f"{credential_name} is not configured or the provider SDK is unavailable.",
                provider_name,
                model,
                language=language_code,
                error_code=exc.error_code,
            )
        if exc.error_code == "GEMINI_REQUEST_FAILED":
            message = f"Gemini request failed ({exc.error_type}). Check the backend log for provider details."
        elif provider_name == "gemini":
            message = f"Gemini API request failed ({exc.error_type}). Check the backend log for provider details."
        else:
            message = f"The configured provider request failed ({exc.error_type}). Check the backend log for provider details."
        return _blocked(validated, "blocked", message, provider_name, model, language=language_code, error_code=exc.error_code)
    except RuntimeError:
        return _blocked(validated, "blocked", "The configured story provider failed. No fallback story was used.", provider_name, model, language=language_code)
    except NarrativeGenerationValidationError as exc:
        return _blocked(validated, "blocked", f"Generation blocked: {exc}", provider_name, model, language=language_code)
    response = {
        "schema_version": SCHEMA_VERSION, "analysis_id": validated["analysis_id"], "video_id": validated["video_id"],
        "mode": validated["performance_mode"]["label"], "status": "generated", "title": title,
        "narrative": narrative, "evidence_coverage": len(used_ids) / len(eligible), "used_event_ids": used_ids,
        "limitations": list(validated["limitations"]), "provider": provider_name, "model": model, "message": None,
        "language": language_code, "presentation_version": STORY_PRESENTATION_VERSION,
    }
    validate_narrative_generation_response(response)
    return response


def validate_narrative_generation_response(response: Any) -> dict[str, Any]:
    """Validate the versioned response contract before it crosses a boundary."""
    if not isinstance(response, dict) or response.get("schema_version") != SCHEMA_VERSION:
        raise NarrativeGenerationValidationError(f"schema_version must be {SCHEMA_VERSION}.")
    required = {"analysis_id", "video_id", "mode", "status", "title", "narrative", "evidence_coverage", "used_event_ids", "limitations", "provider", "model", "language"}
    if not required.issubset(response):
        raise NarrativeGenerationValidationError("Narrative generation response is incomplete.")
    if response["mode"] not in {"pure_dance", "narrative_dance", "evidence_based", "unknown"} or response["status"] not in {"generated", "unavailable", "blocked", "retryable"}:
        raise NarrativeGenerationValidationError("Narrative generation response has an unsupported mode or status.")
    if response["language"] not in _OUTPUT_LANGUAGES:
        raise NarrativeGenerationValidationError("Narrative generation response has an unsupported language.")
    if response["provider"] not in {"ollama", "gemini", "openai"} or not isinstance(response["model"], str) or not response["model"].strip():
        raise NarrativeGenerationValidationError("Narrative generation response has invalid provider metadata.")
    coverage = response["evidence_coverage"]
    if not isinstance(coverage, (int, float)) or isinstance(coverage, bool) or not 0 <= coverage <= 1:
        raise NarrativeGenerationValidationError("evidence_coverage must be between 0 and 1.")
    if not isinstance(response["used_event_ids"], list) or not all(isinstance(item, str) and item for item in response["used_event_ids"]):
        raise NarrativeGenerationValidationError("used_event_ids must be non-empty strings.")
    if response["status"] == "generated":
        if not isinstance(response["title"], str) or not response["title"].strip() or not isinstance(response["narrative"], str) or not response["narrative"].strip():
            raise NarrativeGenerationValidationError("Generated response requires title and narrative text.")
    elif response["title"] is not None or response["narrative"] is not None or response["used_event_ids"] or coverage != 0:
        raise NarrativeGenerationValidationError("Blocked or unavailable responses cannot contain generated evidence.")
    if response["status"] == "retryable":
        retry_after = response.get("retry_after_seconds")
        if retry_after is not None and (not isinstance(retry_after, int) or retry_after < 1):
            raise NarrativeGenerationValidationError("retry_after_seconds must be a positive integer when supplied.")
    return response
