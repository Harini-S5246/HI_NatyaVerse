"""Isolated synthetic demonstration for the verified-evidence Story path.

This service is intentionally separate from uploaded-video analyses.  It
creates only clearly labelled synthetic review records through the existing
submission/review lifecycle, then delegates generation to the package-only
Story integration boundary.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.services.narrative_evidence_review_service import get_review, review_evidence, submit_evidence
from app.services.result_service import get_modality_result
from app.services.story_integration_service import generate_story_for_analysis


DEMONSTRATION_ANALYSIS_ID = "demo-verified-performance-001"
DEMONSTRATION_TITLE = "Demonstration / Sample Verified Performance"
DEMONSTRATION_NOTICE = (
    "This story is generated from explicitly verified demonstration evidence "
    "and is not an interpretation of a real uploaded performance."
)
DEMONSTRATION_STATEMENT = "Synthetic demonstration record: Event one is explicitly verified."


def _submission(status: str) -> dict[str, Any]:
    return {
        "analysis_id": DEMONSTRATION_ANALYSIS_ID,
        "video_id": DEMONSTRATION_ANALYSIS_ID,
        "statement": DEMONSTRATION_STATEMENT,
        "statement_type": "verified_narrative_event",
        "source_reference": "synthetic demonstration source: record-001",
        "submitted_by": "synthetic-demo-curator",
        "verification_method": "synthetic demonstration review",
        "verification_confidence": 1.0,
        "span": {"start_time": 0.0, "end_time": 1.0},
        "provenance": {"type": "expert_verification", "reference": "synthetic-demo-fixture-only"},
        "performance_mode": "narrative_dance",
        "status": status,
    }


def _approval() -> dict[str, Any]:
    return {
        "status": "verified",
        "verified_by": "synthetic-demo-verifier",
        "verification_method": "synthetic demonstration review",
        "verification_confidence": 1.0,
        "production_eligible": True,
        "review_reason": "Synthetic demonstration fixture only; not a real performance.",
    }


def _package() -> dict[str, Any] | None:
    try:
        return get_modality_result(DEMONSTRATION_ANALYSIS_ID, "performance_interpretation")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise


def ensure_demonstration_package() -> dict[str, Any]:
    """Run the existing lifecycle for one explicit synthetic fixture only."""
    package = _package()
    if package is not None:
        return package

    review = get_review(DEMONSTRATION_ANALYSIS_ID)
    records = review.get("records", [])
    # Keep visible lifecycle evidence: a draft and a submitted record are
    # retained, while only the reviewed submitted record reaches the package.
    if not any(record.get("status") == "draft" for record in records):
        submit_evidence(DEMONSTRATION_ANALYSIS_ID, _submission("draft"))
    review = get_review(DEMONSTRATION_ANALYSIS_ID)
    submitted = next((record for record in review["records"] if record.get("status") == "submitted"), None)
    if submitted is None:
        submitted = submit_evidence(DEMONSTRATION_ANALYSIS_ID, _submission("submitted"))
    _, package = review_evidence(DEMONSTRATION_ANALYSIS_ID, submitted["evidence_id"], _approval())
    if package is None:
        raise RuntimeError("Synthetic demonstration evidence did not create a production package.")
    return package


def generate_demonstration_story() -> dict[str, Any]:
    """Generate only through the regular package-only Gemini Story boundary."""
    package = ensure_demonstration_package()
    story = generate_story_for_analysis(DEMONSTRATION_ANALYSIS_ID)
    return {
        "demonstration": True,
        "analysis_id": DEMONSTRATION_ANALYSIS_ID,
        "title": DEMONSTRATION_TITLE,
        "notice": DEMONSTRATION_NOTICE,
        "story": story,
        "evidence_used": [
            {"event_id": event["event_id"], "statement": event["statement"], "type": event["type"]}
            for event in package["events"]
        ],
    }
