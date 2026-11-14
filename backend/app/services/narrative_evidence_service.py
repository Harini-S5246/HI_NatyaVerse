"""Validation boundary for independently curated narrative evidence.

This module intentionally does not read model output, fusion artifacts, or the
Mudra knowledge base.  It only loads explicit human/source-backed annotations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.utils.json_utils import load_json

SCHEMA_VERSION = "1.1.0"
_SOURCE_TYPES = {"expert_annotation", "primary_text_annotation", "scholarly_annotation", "synthetic_test_fixture"}
_STATUSES = {"verified", "unverified", "unknown"}
_CLAIMS = ("subject", "action", "object", "target", "location", "state")
_PERFORMANCE_MODES = {"pure_dance", "narrative_dance", "unknown"}


class NarrativeEvidenceValidationError(ValueError):
    """Raised when a record would turn unsourced data into a narrative claim."""


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NarrativeEvidenceValidationError(f"{field} must be a non-empty string.")
    return value


def _validate_evidence(items: Any, field: str) -> None:
    if not isinstance(items, list) or not items:
        raise NarrativeEvidenceValidationError(f"{field} must be a non-empty evidence list.")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise NarrativeEvidenceValidationError(f"{field}[{index}] must be an object.")
        _require_string(item.get("source"), f"{field}[{index}].source")
        _require_string(item.get("source_reference"), f"{field}[{index}].source_reference")
        _require_string(item.get("notes"), f"{field}[{index}].notes")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise NarrativeEvidenceValidationError(f"{field}[{index}].confidence must be between 0 and 1.")


def _validate_claim(event: dict[str, Any], field: str) -> None:
    claim = event.get(field)
    if not isinstance(claim, dict):
        raise NarrativeEvidenceValidationError(f"event.{field} must be an object with verification_status.")
    status = claim.get("verification_status")
    if status not in _STATUSES:
        raise NarrativeEvidenceValidationError(f"event.{field}.verification_status is required and must be known.")
    label = claim.get("label")
    if label is not None and not isinstance(label, str):
        raise NarrativeEvidenceValidationError(f"event.{field}.label must be a string or null.")
    if status == "verified" and (not isinstance(label, str) or not label.strip()):
        raise NarrativeEvidenceValidationError(f"event.{field} cannot be verified without a label.")
    if status == "unknown" and label is not None:
        raise NarrativeEvidenceValidationError(f"event.{field} is unknown and must have a null label.")
    if status == "unverified" and label is not None:
        raise NarrativeEvidenceValidationError(f"event.{field} is unverified and cannot carry a narrative label.")


def _validate_relation(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise NarrativeEvidenceValidationError(f"event.{field} must be an object or null.")
    _require_string(value.get("label"), f"event.{field}.label")
    if value.get("verification_status") not in {"verified", "unverified"}:
        raise NarrativeEvidenceValidationError(f"event.{field}.verification_status must be verified or unverified.")
    _validate_evidence(value.get("evidence"), f"event.{field}.evidence")


def _validate_performance_mode(value: Any) -> None:
    """Validate independently sourced mode without deriving it from analysis data."""
    if not isinstance(value, dict):
        raise NarrativeEvidenceValidationError("performance_mode must be an object.")
    label = value.get("label")
    status = value.get("verification_status")
    if label not in _PERFORMANCE_MODES:
        raise NarrativeEvidenceValidationError("performance_mode.label is not supported.")
    if label == "unknown" and status != "unknown":
        raise NarrativeEvidenceValidationError("unknown performance_mode must have unknown verification_status.")
    if label in {"pure_dance", "narrative_dance"} and status != "verified":
        raise NarrativeEvidenceValidationError("known performance_mode must have verified verification_status.")
    _require_string(value.get("source"), "performance_mode.source")
    _require_string(value.get("source_reference"), "performance_mode.source_reference")
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise NarrativeEvidenceValidationError("performance_mode.confidence must be between 0 and 1.")


def validate_narrative_evidence(record: Any, *, for_production: bool = False) -> dict[str, Any]:
    """Validate and return ``record`` unchanged; no claims are inferred or filled."""
    if not isinstance(record, dict):
        raise NarrativeEvidenceValidationError("Narrative evidence must be a JSON object.")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise NarrativeEvidenceValidationError(f"schema_version must be {SCHEMA_VERSION}.")
    for field in ("story_id", "story_title", "source", "source_reference", "version"):
        _require_string(record.get(field), field)
    source_type = record.get("source_type")
    if source_type not in _SOURCE_TYPES:
        raise NarrativeEvidenceValidationError("source_type is not supported.")
    production_eligible = record.get("production_eligible")
    if not isinstance(production_eligible, bool):
        raise NarrativeEvidenceValidationError("production_eligible must be boolean.")
    if source_type == "synthetic_test_fixture" and production_eligible:
        raise NarrativeEvidenceValidationError("Synthetic fixtures can never be production eligible.")
    if for_production and (source_type == "synthetic_test_fixture" or not production_eligible):
        raise NarrativeEvidenceValidationError("This record is not eligible for production narrative evidence.")
    _validate_performance_mode(record.get("performance_mode"))

    events = record.get("events")
    if not isinstance(events, list):
        raise NarrativeEvidenceValidationError("events must be an array.")
    previous_start: float | None = None
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise NarrativeEvidenceValidationError(f"events[{index}] must be an object.")
        event_id = _require_string(event.get("event_id"), f"events[{index}].event_id")
        if event_id in event_ids:
            raise NarrativeEvidenceValidationError(f"Duplicate event_id: {event_id}.")
        event_ids.add(event_id)
        start, end = event.get("start_time"), event.get("end_time")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in (start, end)):
            raise NarrativeEvidenceValidationError(f"events[{index}] timestamps must be numbers.")
        if start < 0 or end < start:
            raise NarrativeEvidenceValidationError(f"events[{index}] has invalid timestamp bounds.")
        if previous_start is not None and start < previous_start:
            raise NarrativeEvidenceValidationError("events must be ordered by non-decreasing start_time.")
        previous_start = float(start)
        for field in _CLAIMS:
            _validate_claim(event, field)
        relationships = event.get("relationships")
        if not isinstance(relationships, list):
            raise NarrativeEvidenceValidationError(f"events[{index}].relationships must be an array.")
        for relation_index, relation in enumerate(relationships):
            _validate_relation(relation, f"relationships[{relation_index}]")
        _validate_relation(event.get("temporal_relation"), "temporal_relation")
        _validate_relation(event.get("causal_relation"), "causal_relation")
        _validate_evidence(event.get("evidence"), f"events[{index}].evidence")
    return record


def can_generate_narrative_story(record: Any) -> bool:
    """Return eligibility only; this does not generate text or inspect ML output.

    Both known modes require at least one independently verified narrative
    event. Unknown mode is always blocked. A pure-dance record with no such
    event remains blocked, rather than being turned into a story by default.
    """
    validated = validate_narrative_evidence(record)
    if validated["performance_mode"]["label"] == "unknown":
        return False
    return any(
        any(event[field]["verification_status"] == "verified" for field in _CLAIMS)
        for event in validated["events"]
    )


def load_narrative_evidence(path: Path, *, for_production: bool = False) -> dict[str, Any]:
    """Load a record from disk and validate it without mutating it."""
    return validate_narrative_evidence(load_json(path), for_production=for_production)
