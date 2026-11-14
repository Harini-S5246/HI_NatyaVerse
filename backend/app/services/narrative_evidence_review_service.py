"""Human review ledger for narrative evidence; it never reads inference output."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.errors import AppError
from app.services.performance_interpretation_service import build_from_verified_narrative_evidence
from app.services.result_service import get_modality_result, save_modality_result

logger = logging.getLogger(__name__)

def _log_evidence_event(event: str, analysis_id: str, evidence_id: str, **extra: Any) -> None:
    """Structured log for narrative evidence lifecycle events."""
    logger.info(
        "[NARRATIVE_EVIDENCE_%s] analysis_id=%s evidence_id=%s %s",
        event.upper(),
        analysis_id,
        evidence_id,
        " ".join(f"{k}={v}" for k, v in extra.items()),
    )

SCHEMA_VERSION = "1.0.0"
_STATUSES = {"draft", "submitted", "verified", "rejected"}
_STATEMENT_TYPES = {"verified_narrative_event", "verified_performance_event"}
_MODES = {"pure_dance", "narrative_dance"}
_DRAFT_MODES = _MODES | {"unknown"}
_SOURCE_TYPES = {"curated_annotation", "expert_verification", "trusted_source_annotation", "analysis_summary_candidate"}
_CANDIDATE_ORIGINS = {"human_submitted", "ai_assisted"}


class NarrativeEvidenceReviewValidationError(ValueError):
    """Raised when a human record cannot be traced or safely reviewed."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NarrativeEvidenceReviewValidationError(f"{field} must be a non-empty string.")
    return value.strip()


def _confidence(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise NarrativeEvidenceReviewValidationError(f"{field} must be between 0 and 1.")
    return float(value)


def _span(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"start_time", "end_time"}:
        raise NarrativeEvidenceReviewValidationError("span must contain start_time and end_time.")
    start, end = value["start_time"], value["end_time"]
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) or item < 0 for item in (start, end)) or end < start:
        raise NarrativeEvidenceReviewValidationError("span has invalid timestamp bounds.")
    return {"start_time": float(start), "end_time": float(end)}


def _provenance(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"type", "reference"} or value.get("type") not in _SOURCE_TYPES:
        raise NarrativeEvidenceReviewValidationError("provenance must identify a supported traceable source.")
    return {"type": value["type"], "reference": _text(value.get("reference"), "provenance.reference")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger(analysis_id: str, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = _now()
    return {"schema_version": SCHEMA_VERSION, "analysis_id": analysis_id, "video_id": analysis_id, "records": records or [], "created_at": now, "updated_at": now}


def _load(analysis_id: str) -> dict[str, Any]:
    try:
        ledger = get_modality_result(analysis_id, "narrative_evidence_review")
    except AppError as exc:
        if exc.code != "MODALITY_RESULT_NOT_FOUND":
            raise
        return _ledger(analysis_id)
    if not isinstance(ledger, dict) or ledger.get("analysis_id") != analysis_id or ledger.get("video_id") != analysis_id:
        raise NarrativeEvidenceReviewValidationError("Narrative evidence review belongs to a different analysis.")
    return ledger


def submit_evidence(analysis_id: str, payload: Any) -> dict[str, Any]:
    """Store a draft/submission without assigning verification or eligibility."""
    if not isinstance(payload, dict):
        raise NarrativeEvidenceReviewValidationError("Evidence submission must be an object.")
    required = {"analysis_id", "video_id", "statement", "statement_type", "source_reference", "submitted_by", "verification_method", "verification_confidence", "span", "provenance", "performance_mode", "status"}
    allowed = required | {"candidate_origin"}
    if not required.issubset(payload) or not set(payload).issubset(allowed):
        raise NarrativeEvidenceReviewValidationError("Evidence submission has unsupported fields.")
    if payload.get("analysis_id") != analysis_id or payload.get("video_id") != analysis_id:
        raise NarrativeEvidenceReviewValidationError("Evidence submission belongs to a different analysis.")
    status = payload.get("status")
    if status not in {"draft", "submitted"}:
        raise NarrativeEvidenceReviewValidationError("New evidence must be draft or submitted; it cannot self-verify.")
    if payload.get("statement_type") not in _STATEMENT_TYPES or payload.get("performance_mode") not in _DRAFT_MODES:
        raise NarrativeEvidenceReviewValidationError("statement_type or performance_mode is unsupported.")
    if payload["performance_mode"] == "narrative_dance" and payload["statement_type"] != "verified_narrative_event":
        raise NarrativeEvidenceReviewValidationError("Narrative dance submissions must use verified_narrative_event.")
    candidate_origin = payload.get("candidate_origin", "human_submitted")
    if candidate_origin not in _CANDIDATE_ORIGINS:
        raise NarrativeEvidenceReviewValidationError("candidate_origin is unsupported.")
    if payload["performance_mode"] == "unknown" and payload["status"] != "draft":
        raise NarrativeEvidenceReviewValidationError("Evidence with an unknown performance mode must remain a draft until a reviewer classifies it.")
    now = _now()
    record = {
        "evidence_id": str(uuid4()), "analysis_id": analysis_id, "video_id": analysis_id,
        "statement": _text(payload.get("statement"), "statement"), "statement_type": payload["statement_type"],
        "source_reference": _text(payload.get("source_reference"), "source_reference"),
        "submitted_by": _text(payload.get("submitted_by"), "submitted_by"), "submitted_at": now,
        "verification_method": _text(payload.get("verification_method"), "verification_method"),
        "verification_confidence": _confidence(payload.get("verification_confidence"), "verification_confidence"),
        "span": _span(payload.get("span")), "provenance": _provenance(payload.get("provenance")),
        "performance_mode": payload["performance_mode"], "status": status,
        "candidate_origin": candidate_origin,
        "verified_by": None, "verified_at": None, "production_eligibility": {"status": "ineligible"}, "review_reason": None,
    }
    ledger = _load(analysis_id)
    ledger["records"].append(record)
    ledger["updated_at"] = now
    save_modality_result(analysis_id, "narrative_evidence_review", ledger)
    _log_evidence_event("CREATED", analysis_id, record["evidence_id"], status=status, mode=payload["performance_mode"])
    return record


def update_draft_evidence(analysis_id: str, evidence_id: str, payload: Any) -> dict[str, Any]:
    """Allow a human to edit an AI-assisted draft before it enters review."""
    if not isinstance(payload, dict) or set(payload) != {"statement", "performance_mode"}:
        raise NarrativeEvidenceReviewValidationError("Draft update must contain only statement and performance_mode.")
    if payload.get("performance_mode") not in _DRAFT_MODES:
        raise NarrativeEvidenceReviewValidationError("performance_mode is unsupported.")
    ledger = _load(analysis_id)
    record = next((item for item in ledger["records"] if item.get("evidence_id") == evidence_id), None)
    if record is None or record.get("analysis_id") != analysis_id:
        raise NarrativeEvidenceReviewValidationError("Evidence record was not found for this analysis.")
    if record.get("status") != "draft":
        raise NarrativeEvidenceReviewValidationError("Only draft evidence can be edited.")
    record["statement"] = _text(payload.get("statement"), "statement")
    record["performance_mode"] = payload["performance_mode"]
    ledger["updated_at"] = _now()
    save_modality_result(analysis_id, "narrative_evidence_review", ledger)
    _log_evidence_event("UPDATED", analysis_id, evidence_id, mode=record["performance_mode"])
    return record


def submit_for_review(analysis_id: str, evidence_id: str) -> dict[str, Any]:
    """Move one persisted curator draft to submitted review state.

    This is intentionally a state transition, rather than a shortcut to
    verification.  Only a submitted record may receive a reviewer decision.
    """
    ledger = _load(analysis_id)
    record = next((item for item in ledger["records"] if item.get("evidence_id") == evidence_id), None)
    if record is None or record.get("analysis_id") != analysis_id or record.get("video_id") != analysis_id:
        raise NarrativeEvidenceReviewValidationError("Evidence record was not found for this analysis.")
    if record.get("status") != "draft":
        raise NarrativeEvidenceReviewValidationError("Only draft evidence can be submitted for review.")
    if record.get("performance_mode") not in _MODES:
        raise NarrativeEvidenceReviewValidationError("Select pure dance or narrative dance before submitting evidence for review.")
    now = _now()
    record["status"] = "submitted"
    record["submitted_at"] = now
    ledger["updated_at"] = now
    save_modality_result(analysis_id, "narrative_evidence_review", ledger)
    _log_evidence_event("SUBMITTED", analysis_id, evidence_id, mode=record["performance_mode"])
    return record


def review_evidence(analysis_id: str, evidence_id: str, payload: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply an explicit human verification/rejection decision to one record."""
    if not isinstance(payload, dict) or set(payload) != {"status", "verified_by", "verification_method", "verification_confidence", "production_eligible", "review_reason"}:
        raise NarrativeEvidenceReviewValidationError("Review has unsupported fields.")
    status = payload.get("status")
    if status not in {"verified", "rejected"}:
        raise NarrativeEvidenceReviewValidationError("Review status must be verified or rejected.")
    ledger = _load(analysis_id)
    record = next((item for item in ledger["records"] if item.get("evidence_id") == evidence_id), None)
    if record is None:
        raise NarrativeEvidenceReviewValidationError("Evidence record was not found for this analysis.")
    if record.get("analysis_id") != analysis_id or record.get("video_id") != analysis_id:
        raise NarrativeEvidenceReviewValidationError("Evidence record belongs to a different analysis.")
    if record.get("status") != "submitted":
        raise NarrativeEvidenceReviewValidationError("Only submitted evidence can be reviewed.")
    now = _now()
    if status == "verified":
        record.update({"status": "verified", "verified_by": _text(payload.get("verified_by"), "verified_by"), "verified_at": now,
                       "verification_method": _text(payload.get("verification_method"), "verification_method"),
                       "verification_confidence": _confidence(payload.get("verification_confidence"), "verification_confidence"),
                       "production_eligibility": {"status": "eligible" if payload.get("production_eligible") is True else "ineligible"},
                       "review_reason": _text(payload.get("review_reason"), "review_reason")})
    else:
        record.update({"status": "rejected", "verified_by": _text(payload.get("verified_by"), "verified_by"), "verified_at": now,
                       "production_eligibility": {"status": "ineligible"}, "review_reason": _text(payload.get("review_reason"), "review_reason")})
    ledger["updated_at"] = now
    save_modality_result(analysis_id, "narrative_evidence_review", ledger)
    package = _compile(analysis_id, ledger)
    if package is not None:
        save_modality_result(analysis_id, "performance_interpretation", package)
        _log_evidence_event("PACKAGE_CREATED", analysis_id, evidence_id, fingerprint=package.get("package_fingerprint", "unknown"))
    _log_evidence_event("VERIFIED" if status == "verified" else "REJECTED", analysis_id, evidence_id, production_eligible=record["production_eligibility"]["status"] == "eligible", package_created=package is not None)
    return record, package


def get_review(analysis_id: str) -> dict[str, Any]:
    ledger = _load(analysis_id)
    eligible = [item for item in ledger["records"] if item.get("status") == "verified" and item.get("production_eligibility") == {"status": "eligible"}]
    return {**ledger, "story_eligible": bool(eligible), "story_eligibility_reason": "Eligible verified evidence is available." if eligible else "No verified, production-eligible evidence is available."}


def story_unavailability_reason(analysis_id: str) -> str:
    """Describe the persisted review lifecycle without exposing source payloads."""
    ledger = _load(analysis_id)
    records = ledger["records"]
    if not records:
        return "No narrative evidence review records exist for this performance."
    if any(record.get("status") == "draft" for record in records):
        return "Narrative evidence exists but remains in draft and has not been submitted for review."
    if any(record.get("status") == "submitted" for record in records):
        return "Narrative evidence has been submitted and is awaiting an explicit reviewer decision."
    if any(record.get("status") == "verified" and record.get("production_eligibility") != {"status": "eligible"} for record in records):
        return "Narrative evidence was verified but has not been marked production eligible."
    if any(record.get("status") == "verified" and record.get("production_eligibility") == {"status": "eligible"} for record in records):
        return "Production-eligible narrative evidence exists, but its Performance Interpretation Package is unavailable."
    if any(record.get("status") == "rejected" for record in records):
        return "Narrative evidence was reviewed and rejected; no production-eligible evidence is available."
    return "No verified, production-eligible narrative evidence is available for this performance."


def _compile(analysis_id: str, ledger: dict[str, Any]) -> dict[str, Any] | None:
    records = [item for item in ledger["records"] if item.get("status") == "verified" and item.get("production_eligibility") == {"status": "eligible"}]
    if not records:
        return None
    mode = records[0]["performance_mode"]
    if any(item["performance_mode"] != mode for item in records):
        raise NarrativeEvidenceReviewValidationError("Eligible records disagree on the explicitly supplied performance mode.")
    provenance = records[0]["provenance"]
    artifact = {"schema_version": "1.0.0", "analysis_id": analysis_id, "video_id": analysis_id, "created_at": _now(),
        "performance_mode": {"label": mode, "verification_status": "verified", "source": {"type": provenance["type"], "reference": provenance["reference"]},
                             "provenance": {"source_reference": records[0]["source_reference"], "annotator_or_verifier": records[0]["verified_by"], "method": records[0]["verification_method"], "verification_confidence": records[0]["verification_confidence"]}},
        "records": [{"evidence_id": item["evidence_id"], "analysis_id": analysis_id, "video_id": analysis_id, "statement": item["statement"], "statement_type": item["statement_type"],
                     "source": {"type": item["provenance"]["type"], "reference": item["provenance"]["reference"]},
                     "provenance": {"source_reference": item["source_reference"], "annotator_or_verifier": item["verified_by"], "method": item["verification_method"], "verification_confidence": item["verification_confidence"]},
                     "span": item["span"], "verification_status": "verified", "verification_method": "human_or_curated_source", "production_eligibility": {"status": "eligible"}} for item in records]}
    return build_from_verified_narrative_evidence(analysis_id, artifact)
