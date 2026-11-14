"""Explicit, source-backed narrative evidence; never derived from model output."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.result_service import save_modality_result

SCHEMA_VERSION = "1.0.0"
_SOURCE_TYPES = {"curated_annotation", "expert_verification", "trusted_source_annotation", "analysis_summary_candidate"}
_STATEMENT_TYPES = {"verified_narrative_event", "verified_performance_event"}


class VerifiedNarrativeEvidenceValidationError(ValueError):
    """Raised when an untraceable or non-verified claim is submitted."""


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerifiedNarrativeEvidenceValidationError(f"{field} must be a non-empty string.")
    return value.strip()


def _provenance(value: Any, field: str) -> None:
    if not isinstance(value, dict) or set(value) != {"source_reference", "annotator_or_verifier", "method", "verification_confidence"}:
        raise VerifiedNarrativeEvidenceValidationError(f"{field} is incomplete.")
    for key in ("source_reference", "annotator_or_verifier", "method"):
        _non_empty(value.get(key), f"{field}.{key}")
    confidence = value.get("verification_confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise VerifiedNarrativeEvidenceValidationError(f"{field}.verification_confidence must be between 0 and 1.")


def _source(value: Any, field: str) -> None:
    if not isinstance(value, dict) or set(value) != {"type", "reference"} or value.get("type") not in _SOURCE_TYPES:
        raise VerifiedNarrativeEvidenceValidationError(f"{field} must identify a supported traceable source.")
    _non_empty(value.get("reference"), f"{field}.reference")


def _span(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"start_time", "end_time"}:
        raise VerifiedNarrativeEvidenceValidationError(f"{field} must contain start_time and end_time.")
    start, end = value.get("start_time"), value.get("end_time")
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) or item < 0 for item in (start, end)) or end < start:
        raise VerifiedNarrativeEvidenceValidationError(f"{field} has invalid timestamp bounds.")


def validate_verified_narrative_evidence(artifact: Any, *, expected_analysis_id: str | None = None) -> dict[str, Any]:
    """Validate an isolated artifact without inspecting model, fusion, or audio data."""
    required = {"schema_version", "analysis_id", "video_id", "performance_mode", "records", "created_at"}
    if not isinstance(artifact, dict) or set(artifact) != required or artifact.get("schema_version") != SCHEMA_VERSION:
        raise VerifiedNarrativeEvidenceValidationError("Narrative evidence has an unsupported schema.")
    analysis_id, video_id = artifact.get("analysis_id"), artifact.get("video_id")
    _non_empty(analysis_id, "analysis_id")
    _non_empty(video_id, "video_id")
    if analysis_id != video_id or (expected_analysis_id and analysis_id != expected_analysis_id):
        raise VerifiedNarrativeEvidenceValidationError("Narrative evidence belongs to a different analysis.")
    if not isinstance(artifact.get("created_at"), str):
        raise VerifiedNarrativeEvidenceValidationError("created_at is required.")

    mode = artifact.get("performance_mode")
    if not isinstance(mode, dict) or set(mode) != {"label", "verification_status", "source", "provenance"} or mode.get("label") not in {"pure_dance", "narrative_dance"} or mode.get("verification_status") != "verified":
        raise VerifiedNarrativeEvidenceValidationError("performance_mode must be explicitly verified.")
    _source(mode.get("source"), "performance_mode.source")
    _provenance(mode.get("provenance"), "performance_mode.provenance")

    records = artifact.get("records")
    if not isinstance(records, list) or (mode["label"] == "narrative_dance" and not records):
        raise VerifiedNarrativeEvidenceValidationError("Narrative dance requires at least one verified record.")
    seen: set[str] = set()
    previous_start: float | None = None
    for index, record in enumerate(records):
        expected = {"evidence_id", "analysis_id", "video_id", "statement", "statement_type", "source", "provenance", "span", "verification_status", "verification_method", "production_eligibility"}
        if not isinstance(record, dict) or set(record) != expected:
            raise VerifiedNarrativeEvidenceValidationError(f"records[{index}] has unsupported fields; model and fusion payloads are not accepted.")
        evidence_id = _non_empty(record.get("evidence_id"), f"records[{index}].evidence_id")
        if evidence_id in seen:
            raise VerifiedNarrativeEvidenceValidationError("Narrative evidence IDs must be unique.")
        seen.add(evidence_id)
        if record.get("analysis_id") != analysis_id or record.get("video_id") != video_id:
            raise VerifiedNarrativeEvidenceValidationError("Narrative evidence record belongs to a different analysis.")
        _non_empty(record.get("statement"), f"records[{index}].statement")
        if record.get("statement_type") not in _STATEMENT_TYPES:
            raise VerifiedNarrativeEvidenceValidationError("Narrative evidence statement_type is unsupported.")
        if mode["label"] == "narrative_dance" and record["statement_type"] != "verified_narrative_event":
            raise VerifiedNarrativeEvidenceValidationError("Narrative dance accepts only verified_narrative_event records.")
        if record.get("verification_status") != "verified" or record.get("verification_method") != "human_or_curated_source" or record.get("production_eligibility") != {"status": "eligible"}:
            raise VerifiedNarrativeEvidenceValidationError("Only explicitly verified, production-eligible narrative evidence is accepted.")
        _source(record.get("source"), f"records[{index}].source")
        _provenance(record.get("provenance"), f"records[{index}].provenance")
        _span(record.get("span"), f"records[{index}].span")
        if record["span"] is not None:
            start = float(record["span"]["start_time"])
            if previous_start is not None and start < previous_start:
                raise VerifiedNarrativeEvidenceValidationError("Narrative evidence records must be in timestamp order.")
            previous_start = start
    return artifact


def create_verified_narrative_evidence(analysis_id: str, payload: Any) -> dict[str, Any]:
    """Create and persist only caller-supplied, explicitly verified statements."""
    if not isinstance(payload, dict):
        raise VerifiedNarrativeEvidenceValidationError("Narrative evidence payload must be an object.")
    artifact = {**payload, "schema_version": SCHEMA_VERSION, "created_at": datetime.now(timezone.utc).isoformat()}
    validate_verified_narrative_evidence(artifact, expected_analysis_id=analysis_id)
    save_modality_result(analysis_id, "narrative_evidence", artifact)
    return artifact
