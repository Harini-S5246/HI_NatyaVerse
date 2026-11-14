"""Explicit endpoint for source-backed narrative evidence creation."""
from typing import Any

from fastapi import APIRouter, Body

from app.core.errors import AppError
from app.services.performance_interpretation_service import build_from_verified_narrative_evidence
from app.services.result_service import save_modality_result
from app.services.upload_service import get_uploaded_video_path
from app.services.verified_narrative_evidence_service import (
    VerifiedNarrativeEvidenceValidationError,
    create_verified_narrative_evidence,
)
from app.services.narrative_evidence_review_service import (
    NarrativeEvidenceReviewValidationError,
    get_review,
    review_evidence,
    submit_evidence,
    submit_for_review,
    update_draft_evidence,
)
from app.services.narrative_evidence_candidate_service import NarrativeEvidenceCandidateError, prepare_candidates

router = APIRouter(prefix="/api", tags=["Narrative Evidence"])


@router.post("/videos/{analysis_id}/narrative-evidence")
def create_narrative_evidence(analysis_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    get_uploaded_video_path(analysis_id)
    # Preserve the original explicitly-verified artifact API. New human
    # annotations use the submission ledger and cannot self-verify.
    if "records" not in payload:
        try:
            record = submit_evidence(analysis_id, payload)
        except NarrativeEvidenceReviewValidationError as exc:
            raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc
        return {"narrative_evidence": record, "story_eligible": False, "story_eligibility_reason": "Submitted evidence requires explicit review."}
    try:
        artifact = create_verified_narrative_evidence(analysis_id, payload)
        package = build_from_verified_narrative_evidence(analysis_id, artifact)
    except VerifiedNarrativeEvidenceValidationError as exc:
        raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc
    save_modality_result(analysis_id, "performance_interpretation", package)
    return {"narrative_evidence": artifact, "performance_interpretation": package}


@router.get("/videos/{analysis_id}/narrative-evidence")
def get_narrative_evidence_review(analysis_id: str) -> dict[str, Any]:
    get_uploaded_video_path(analysis_id)
    try:
        return get_review(analysis_id)
    except NarrativeEvidenceReviewValidationError as exc:
        raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc


@router.post("/videos/{analysis_id}/narrative-evidence/candidates")
def prepare_narrative_evidence_candidates(analysis_id: str) -> dict[str, Any]:
    get_uploaded_video_path(analysis_id)
    try:
        return {"analysis_id": analysis_id, "candidates": prepare_candidates(analysis_id)}
    except NarrativeEvidenceCandidateError as exc:
        raise AppError(str(exc), 422, "NARRATIVE_EVIDENCE_CANDIDATES_UNAVAILABLE") from exc


@router.patch("/videos/{analysis_id}/narrative-evidence/{evidence_id}")
def update_narrative_evidence_draft(analysis_id: str, evidence_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    get_uploaded_video_path(analysis_id)
    try:
        return {"narrative_evidence": update_draft_evidence(analysis_id, evidence_id, payload)}
    except NarrativeEvidenceReviewValidationError as exc:
        raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc


@router.post("/videos/{analysis_id}/narrative-evidence/{evidence_id}/review")
def review_narrative_evidence(analysis_id: str, evidence_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    get_uploaded_video_path(analysis_id)
    try:
        record, package = review_evidence(analysis_id, evidence_id, payload)
    except NarrativeEvidenceReviewValidationError as exc:
        raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc
    return {"narrative_evidence": record, "performance_interpretation": package, "story_eligible": package is not None}


@router.post("/videos/{analysis_id}/narrative-evidence/{evidence_id}/submit")
def submit_narrative_evidence_for_review(analysis_id: str, evidence_id: str) -> dict[str, Any]:
    """Explicitly advance a curator draft to the reviewer queue."""
    get_uploaded_video_path(analysis_id)
    try:
        record = submit_for_review(analysis_id, evidence_id)
    except NarrativeEvidenceReviewValidationError as exc:
        raise AppError(str(exc), 422, "INVALID_NARRATIVE_EVIDENCE") from exc
    return {"narrative_evidence": record, "story_eligible": False}
