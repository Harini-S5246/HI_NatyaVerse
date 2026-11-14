"""Prepare review-only narrative evidence candidates from completed summaries.

Candidates are deliberately drafts.  They never invoke an LLM and they never
read raw frames or promote model output into production evidence.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.errors import AppError
from app.services.narrative_evidence_review_service import submit_evidence
from app.services.result_service import get_result

logger = logging.getLogger(__name__)


class NarrativeEvidenceCandidateError(ValueError):
    """Raised when a completed analysis lacks a usable validated summary."""


def _summary(result: Any, analysis_id: str) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("analysis_id") != analysis_id or result.get("video_id") != analysis_id:
        raise NarrativeEvidenceCandidateError("Completed analysis result belongs to a different analysis.")
    if result.get("status") != "completed":
        raise NarrativeEvidenceCandidateError("Evidence candidates can be prepared only after analysis is completed.")
    summary = result.get("summary")
    required = ("dominant_mudra", "dominant_bhava", "mudra_event_count", "bhava_event_count", "frame_count")
    if not isinstance(summary, dict) or any(not isinstance(summary.get(key), (str, int, float)) or isinstance(summary.get(key), bool) for key in required):
        raise NarrativeEvidenceCandidateError("Completed analysis does not contain a validated summary suitable for a review candidate.")
    if not isinstance(summary["dominant_mudra"], str) or not summary["dominant_mudra"].strip() or not isinstance(summary["dominant_bhava"], str) or not summary["dominant_bhava"].strip():
        raise NarrativeEvidenceCandidateError("Completed analysis summary has no usable dominant observations.")
    return summary


def prepare_candidates(analysis_id: str) -> list[dict[str, Any]]:
    """Persist concise, AI-assisted drafts sourced solely from ``result.summary``."""
    try:
        result = get_result(analysis_id)
    except AppError as exc:
        if exc.code == "RESULT_NOT_FOUND":
            raise NarrativeEvidenceCandidateError("Completed analysis result was not found.") from exc
        raise
    summary = _summary(result, analysis_id)
    statement = (
        f"The completed analysis summary records {summary['dominant_mudra']} as the dominant Mudra "
        f"and {summary['dominant_bhava']} as the most common predicted emotion label "
        f"across {summary['frame_count']} sampled frames."
    )
    candidate = submit_evidence(analysis_id, {
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "statement": statement,
        "statement_type": "verified_narrative_event",
        "source_reference": f"analysis_result:{analysis_id}#summary",
        "submitted_by": "AI-assisted candidate preparation",
        "verification_method": "Derived only from persisted completed analysis summary; requires human review",
        "verification_confidence": 0.0,
        "span": None,
        "provenance": {"type": "analysis_summary_candidate", "reference": f"analysis_result:{analysis_id}#summary"},
        # The analysis summary does not establish performance mode.  A human
        # must choose one while editing this draft before it can be submitted.
        "performance_mode": "unknown",
        "status": "draft",
        "candidate_origin": "ai_assisted",
    })
    logger.info("Narrative evidence candidates prepared: analysis_id=%s candidate_count=1 evidence_ids=%s", analysis_id, [candidate["evidence_id"]])
    return [candidate]
