"""Story adapter for verified narratives and real, cautious model interpretations."""
from __future__ import annotations

import logging
import hashlib
import json
import uuid
from threading import Lock
from typing import Any

from app.core.errors import AppError
from app.services.narrative_generation_service import (
    NarrativeGenerationValidationError,
    STORY_PRESENTATION_VERSION,
    configured_provider_metadata,
    generate_narrative,
    normalize_output_language,
    validate_narrative_generation_response,
)
from app.services.performance_interpretation_service import (
    PerformanceInterpretationValidationError,
    build_analysis_observation_interpretation,
    validate_performance_interpretation,
)
from app.services.result_service import get_modality_result, save_modality_result
from app.services.narrative_evidence_review_service import story_unavailability_reason

logger = logging.getLogger(__name__)
_generation_locks: dict[str, Lock] = {}
_locks_guard = Lock()


def _log_story_event(event: str, analysis_id: str, **extra: Any) -> None:
    """Structured log for story generation lifecycle events."""
    logger.info(
        "[STORY_%s] analysis_id=%s %s",
        event.upper(),
        analysis_id,
        " ".join(f"{k}={v}" for k, v in extra.items()),
    )


def _package_fingerprint(package: dict[str, Any]) -> str:
    """Stable identity for a validated package, used only for story caching."""
    return hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _lock_for(key: str) -> Lock:
    with _locks_guard:
        return _generation_locks.setdefault(key, Lock())


def _package_video_id(package: dict[str, Any], *, fallback: str) -> str:
    """Resolve the concrete video identity for a validated package without trusting stale aliases."""
    if not isinstance(package, dict):
        return fallback
    video_id = package.get("video_id")
    if isinstance(video_id, str) and video_id.strip():
        return video_id
    analysis_id = package.get("analysis_id")
    if isinstance(analysis_id, str) and analysis_id.strip():
        return analysis_id
    return fallback


def _unavailable(analysis_id: str, message: str, *, language: str = "en", status: str = "unavailable", package_fingerprint: str | None = None, package_evidence_coverage: float = 0.0, video_id: str | None = None) -> dict[str, Any]:
    """Return a contract-valid, evidence-limited response for this exact ID."""
    _, provider_name, model = configured_provider_metadata()
    resolved_video_id = video_id or analysis_id
    response = {
        "schema_version": "1.0.0",
        "analysis_id": analysis_id,
        "video_id": resolved_video_id,
        "mode": "unknown",
        "status": status,
        "language": language,
        "title": None,
        "narrative": None,
        "evidence_coverage": 0.0,
        "used_event_ids": [],
        "limitations": [message],
        "provider": provider_name,
        "model": model,
        "message": message,
        "package_eligible": package_fingerprint is not None,
        "package_fingerprint": package_fingerprint,
        "package_evidence_coverage": package_evidence_coverage,
    }
    return validate_narrative_generation_response(response)


def _with_package_state(story: dict[str, Any], fingerprint: str, package: dict[str, Any]) -> dict[str, Any]:
    """Attach read-only package state to an API response, never to its cache."""
    response = dict(story)
    response["package_eligible"] = True
    response["package_fingerprint"] = fingerprint
    response["package_evidence_coverage"] = _package_evidence_coverage(package)
    return response


def _package_evidence_coverage(package: dict[str, Any]) -> float:
    coverage = package.get("evidence_coverage", {})
    if not isinstance(coverage, dict):
        return 0.0
    observations = coverage.get("analysis_observation_events", 0)
    total = coverage.get("total_timeline_rows", 0)
    if (
        isinstance(observations, int)
        and not isinstance(observations, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total > 0
    ):
        return min(1.0, max(0.0, observations / total))
    verified_records = coverage.get("eligible_verified_records", 0)
    return 1.0 if isinstance(verified_records, int) and verified_records > 0 else 0.0


def _is_uploaded_video_id(analysis_id: str) -> bool:
    try:
        return str(uuid.UUID(analysis_id)) == analysis_id
    except (ValueError, AttributeError, TypeError):
        return False


def _is_model_observation_package(package: dict[str, Any]) -> bool:
    mode = package.get("performance_mode")
    events = package.get("events")
    return (
        isinstance(mode, dict) and mode.get("source") == "fusion_analysis"
    ) or (
        isinstance(events, list)
        and any(isinstance(event, dict) and event.get("type") == "recorded_model_observation" for event in events)
    )


def _load_package(analysis_id: str) -> dict[str, Any] | None:
    try:
        package = get_modality_result(analysis_id, "performance_interpretation")
    except AppError as exc:
        if exc.code != "MODALITY_RESULT_NOT_FOUND":
            raise
        return None
    if not isinstance(package, dict):
        raise AppError("Performance interpretation is not a valid object.", 409, "INVALID_PERFORMANCE_INTERPRETATION")
    package_video_id = _package_video_id(package, fallback=analysis_id)
    if package.get("analysis_id") != analysis_id and package_video_id != analysis_id:
        raise AppError("Performance interpretation does not belong to this analysis.", 409, "ANALYSIS_ID_MISMATCH")
    if package_video_id != package.get("analysis_id") and package.get("video_id") not in {None, analysis_id, package_video_id}:
        raise AppError("Performance interpretation does not belong to this analysis.", 409, "ANALYSIS_ID_MISMATCH")
    # Older builds persisted model predictions as if they were verified
    # annotations. Rebuild these from the current real analysis artifacts.
    if _is_model_observation_package(package):
        return None
    try:
        validate_performance_interpretation(package, for_production=True)
    except PerformanceInterpretationValidationError as exc:
        raise AppError("Stored performance interpretation is not production eligible.", 409, "INVALID_PERFORMANCE_INTERPRETATION") from exc
    return package


def _get_or_build_package(analysis_id: str) -> dict[str, Any] | None:
    """Load verified evidence or compile current observations for this upload."""
    package = _load_package(analysis_id)
    if package is not None:
        return package

    # Non-UUID identifiers are used by isolated tests and demonstrations.
    # They can use an explicitly reviewed package, but never raw modality data.
    if not _is_uploaded_video_id(analysis_id):
        return None

    try:
        fusion_result = get_modality_result(analysis_id, "fusion")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise
    try:
        mudra_result = get_modality_result(analysis_id, "mudra")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise
    try:
        bhava_result = get_modality_result(analysis_id, "bhava")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise

    pose_result = None
    try:
        pose_result = get_modality_result(analysis_id, "pose_events")
    except AppError as exc:
        if exc.code != "MODALITY_RESULT_NOT_FOUND":
            raise

    audio_result = None
    try:
        audio_result = get_modality_result(analysis_id, "audio_evidence")
    except AppError as exc:
        if exc.code != "MODALITY_RESULT_NOT_FOUND":
            raise

    try:
        package = build_analysis_observation_interpretation(
            analysis_id,
            fusion_result,
            mudra_result,
            bhava_result,
            pose_result=pose_result,
            audio_result=audio_result,
        )
    except PerformanceInterpretationValidationError as exc:
        raise AppError(str(exc), 409, "INVALID_ANALYSIS_EVIDENCE") from exc

    logger.info(
        "[STORY] video_id=%s analysis_id=%s evidence_found=True timeline_count=%s narrative_segments=%s synthetic_fixture=False",
        analysis_id,
        analysis_id,
        len(fusion_result.get("timeline", [])),
        len(package.get("events", [])),
    )
    return package


def _cached_story(analysis_id: str, fingerprint: str, language: str = "en", *, video_id: str | None = None) -> dict[str, Any] | None:
    try:
        cached = get_modality_result(analysis_id, "story_generation")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise
    if not isinstance(cached, dict):
        logger.info("[STORY_CACHE_MISS] analysis_id=%s reason=invalid-cache-shape", analysis_id)
        return None
    stored_fingerprint = cached.get("package_fingerprint")
    stored_video_id = cached.get("video_id") if isinstance(cached.get("video_id"), str) else None
    logger.info("[STORY_CACHE_CHECK] analysis_id=%s requested_fingerprint=%s stored_fingerprint=%s stored_video_id=%s", analysis_id, fingerprint, stored_fingerprint, stored_video_id)
    if stored_fingerprint != fingerprint:
        logger.info("[STORY_CACHE_MISS] analysis_id=%s reason=fingerprint-mismatch", analysis_id)
        return None
    if video_id is not None and stored_video_id not in {None, video_id}:
        logger.info("[STORY_CACHE_MISS] analysis_id=%s reason=video-id-mismatch requested_video_id=%s stored_video_id=%s", analysis_id, video_id, stored_video_id)
        return None
    variants = cached.get("story_variants", {})
    story = variants.get(language) if isinstance(variants, dict) else None
    if story is None:
        candidate = cached.get("story")
        if (
            isinstance(candidate, dict)
            and candidate.get("language") == language
            and candidate.get("presentation_version") == STORY_PRESENTATION_VERSION
        ):
            story = candidate
    if (
        not isinstance(story, dict)
        or story.get("analysis_id") != analysis_id
        or story.get("video_id") not in {video_id, analysis_id, None}
        or story.get("status") != "generated"
        or story.get("language") != language
        or story.get("presentation_version") != STORY_PRESENTATION_VERSION
    ):
        logger.info("[STORY_CACHE_MISS] analysis_id=%s reason=stories-do-not-match-request", analysis_id)
        return None
    logger.info("[STORY_CACHE_HIT] analysis_id=%s", analysis_id)
    return validate_narrative_generation_response(story)


def get_existing_story_for_analysis(analysis_id: str, *, language: str = "en") -> dict[str, Any]:
    """Read a generated story only; this function never contacts Gemini."""
    language_code, _ = normalize_output_language(language)
    _log_story_event("GET_REQUESTED", analysis_id)
    package = _get_or_build_package(analysis_id)
    if package is None:
        lifecycle_reason = story_unavailability_reason(analysis_id)
        return _unavailable(analysis_id, f"No real, usable analysis evidence is currently available for this performance. {lifecycle_reason}", language=language_code)
    fingerprint = _package_fingerprint(package)
    video_id = _package_video_id(package, fallback=analysis_id)
    logger.info("[STORY_PACKAGE_FOUND] analysis_id=%s video_id=%s package_fingerprint=%s event_ids=%s", analysis_id, video_id, fingerprint, [event.get("event_id") for event in package.get("events", [])])
    cached = _cached_story(analysis_id, fingerprint, language_code, video_id=video_id)
    if cached is not None:
        return _with_package_state(cached, fingerprint, package)
    return _unavailable(
        analysis_id,
        "Your evidence is ready. Select Generate Story to contact Gemini.",
        language=language_code,
        package_fingerprint=fingerprint,
        package_evidence_coverage=_package_evidence_coverage(package),
        video_id=video_id,
    )


def generate_story_for_analysis(analysis_id: str, *, language: str = "en") -> dict[str, Any]:
    """Generate only from the persisted package belonging to ``analysis_id``."""
    language_code, _ = normalize_output_language(language)
    _log_story_event("GENERATION_REQUESTED", analysis_id)
    package = _get_or_build_package(analysis_id)
    if package is None:
        lifecycle_reason = story_unavailability_reason(analysis_id)
        logger.info(
            "Story unavailable: analysis_id=%s reason=%s",
            analysis_id,
            lifecycle_reason,
        )
        return _unavailable(
            analysis_id,
            "No real, usable analysis evidence is currently available for this performance. "
            f"{lifecycle_reason} The system does not generate unsupported story content.",
            language=language_code,
            video_id=_package_video_id({"analysis_id": analysis_id, "video_id": analysis_id}, fallback=analysis_id),
        )

    fingerprint = _package_fingerprint(package)
    video_id = _package_video_id(package, fallback=analysis_id)
    logger.info("[STORY_PACKAGE_FOUND] analysis_id=%s video_id=%s package_fingerprint=%s event_ids=%s", analysis_id, video_id, fingerprint, [event.get("event_id") for event in package.get("events", [])])
    cached = _cached_story(analysis_id, fingerprint, language_code, video_id=video_id)
    if cached is not None:
        logger.info("Story generation cache hit: analysis_id=%s", analysis_id)
        return _with_package_state(cached, fingerprint, package)
    lock = _lock_for(f"{analysis_id}:{fingerprint}:{language_code}")
    if not lock.acquire(blocking=False):
        return _unavailable(
            analysis_id,
            "Story generation is already in progress for this evidence. Please retry shortly.",
            language=language_code,
            status="retryable",
            package_fingerprint=fingerprint,
            package_evidence_coverage=_package_evidence_coverage(package),
            video_id=_package_video_id(package, fallback=analysis_id),
        )
    try:
        cached = _cached_story(analysis_id, fingerprint, language_code, video_id=video_id)
        if cached is not None:
            return _with_package_state(cached, fingerprint, package)
        logger.info("[STORY_GEMINI_CALL_START] analysis_id=%s package_fingerprint=%s", analysis_id, fingerprint)
        story = generate_narrative(package, language=language_code)
        if story["status"] == "generated":
            logger.info("[STORY_GEMINI_CALL_SUCCESS] analysis_id=%s", analysis_id)
            logger.info("[STORY_VALIDATION_SUCCESS] analysis_id=%s", analysis_id)
            _log_story_event("GENERATION_COMPLETED", analysis_id, status="generated", fingerprint=fingerprint)
        else:
            _log_story_event("GENERATION_FAILED", analysis_id, status=story["status"], message=story.get("message"))
        if story["status"] == "generated":
            try:
                existing = get_modality_result(analysis_id, "story_generation")
            except AppError as exc:
                if exc.code != "MODALITY_RESULT_NOT_FOUND":
                    raise
                existing = {}
            variants = existing.get("story_variants", {}) if isinstance(existing, dict) and existing.get("package_fingerprint") == fingerprint else {}
            variants = dict(variants) if isinstance(variants, dict) else {}
            variants[language_code] = story
            save_modality_result(analysis_id, "story_generation", {
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "package_fingerprint": fingerprint,
                "story": story,
                "story_variants": variants,
            })
            from app.services.result_service import modality_result_path
            logger.info("[STORY_PERSIST_SUCCESS] analysis_id=%s persisted_path=%s package_fingerprint=%s", analysis_id, modality_result_path(analysis_id, "story_generation"), fingerprint)
        return _with_package_state(story, fingerprint, package)
    except NarrativeGenerationValidationError as exc:
        _log_story_event("GENERATION_FAILED", analysis_id, error=str(exc))
        return _unavailable(
            analysis_id,
            "Story generation failed validation. No fallback story was used.",
            language=language_code,
            status="blocked",
            package_fingerprint=fingerprint,
            package_evidence_coverage=_package_evidence_coverage(package),
            video_id=_package_video_id(package, fallback=analysis_id),
        )
    finally:
        lock.release()
