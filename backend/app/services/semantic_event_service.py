"""Phase 1 semantic event composition from existing analysis evidence.

This module adds no new inference. It converts one completed fusion timeline
into a provenance-preserving artifact while leaving unsupported semantics
explicitly unknown.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.services.result_service import (
    get_modality_result,
    save_modality_result,
)


def _evidence_lookup(items: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["label"]): item
        for item in items
        if isinstance(item, dict) and item.get("label")
    }


def _timeline_id(index: int) -> str:
    return f"fusion-timeline-{index:04d}"


def _duration(start_time: Any, end_time: Any) -> float | None:
    if start_time is None or end_time is None:
        return None
    try:
        return float(end_time) - float(start_time)
    except (TypeError, ValueError):
        return None


def compose_semantic_events(analysis_id: str) -> dict[str, Any]:
    """Compose Phase 1 events from the exact stored fusion artifact."""

    fusion = get_modality_result(analysis_id, "fusion")
    if (
        fusion.get("analysis_id") != analysis_id
        or fusion.get("video_id") != analysis_id
    ):
        raise AppError(
            "Fusion result does not belong to the requested analysis.",
            409,
            "ANALYSIS_ID_MISMATCH",
        )

    evidence = fusion.get("evidence", {}) or {}
    grounded = _evidence_lookup(evidence.get("grounded", []) or [])
    unresolved = _evidence_lookup(evidence.get("unresolved", []) or [])
    detected_bhava = _evidence_lookup(evidence.get("detected", []) or [])
    pose_events_by_id: dict[str, dict[str, Any]] = {}
    try:
        pose_artifact = get_modality_result(analysis_id, "pose_events")
        if (
            pose_artifact.get("analysis_id") != analysis_id
            or pose_artifact.get("video_id") != analysis_id
        ):
            raise AppError(
                "Pose result does not belong to the requested analysis.",
                409,
                "ANALYSIS_ID_MISMATCH",
            )
        pose_events_by_id = {
            event.get("event_id"): event
            for event in pose_artifact.get("events", [])
            if isinstance(event, dict) and event.get("event_id")
        }
    except AppError as exc:
        if exc.code != "MODALITY_RESULT_NOT_FOUND":
            raise
    timeline = fusion.get("timeline", []) or []
    events: list[dict[str, Any]] = []

    for index, row in enumerate(timeline, start=1):
        if not isinstance(row, dict):
            continue

        timeline_id = _timeline_id(index)
        mudra_label = row.get("mudra")
        mudra_evidence = grounded.get(mudra_label) or unresolved.get(mudra_label)
        mudra_status = "grounded" if mudra_label in grounded else "unresolved"
        verification_status = (
            mudra_evidence.get("verification_status")
            if mudra_status == "grounded" and mudra_evidence
            else None
        )
        has_source_provenance = bool(
            mudra_evidence
            and verification_status in {"verified", "partially_verified"}
            and mudra_evidence.get("knowledge_status", verification_status) == verification_status
            and isinstance(mudra_evidence.get("claim_id"), str)
            and mudra_evidence["claim_id"].strip()
            and isinstance(mudra_evidence.get("source_references"), list)
            and mudra_evidence["source_references"]
            and all(
                isinstance(reference, str) and reference.strip()
                for reference in mudra_evidence["source_references"]
            )
            and isinstance(mudra_evidence.get("uncertainty_notes"), list)
            and all(isinstance(note, str) for note in mudra_evidence["uncertainty_notes"])
        )
        knowledge_status = (
            mudra_evidence.get("knowledge_status", verification_status)
            if has_source_provenance
            else None
        )
        event_evidence_ids = [timeline_id]
        if mudra_evidence and mudra_evidence.get("id"):
            event_evidence_ids.append(mudra_evidence["id"])

        bhava_label = row.get("bhava")
        bhava_evidence = detected_bhava.get(bhava_label)
        if bhava_evidence and bhava_evidence.get("id"):
            event_evidence_ids.append(bhava_evidence["id"])

        event_id = f"event_{index:04d}"
        pose_event = pose_events_by_id.get(f"pose_event_{index:04d}")
        events.append(
            {
                "event_id": event_id,
                "analysis_id": analysis_id,
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "duration": _duration(row.get("start_time"), row.get("end_time")),
                "subject": None,
                "action": None,
                "object": None,
                "target": None,
                "location": None,
                "mudra": {
                    "label": mudra_label,
                    "meaning": (
                        mudra_evidence.get("detail")
                        if mudra_evidence
                        and verification_status in {"verified", "partially_verified"}
                        and has_source_provenance
                        else None
                    ),
                    "confidence": row.get("mudra_confidence"),
                    "grounding_status": mudra_status,
                    "knowledge_status": knowledge_status,
                    "verification_status": verification_status if has_source_provenance else None,
                    "claim_id": mudra_evidence.get("claim_id") if has_source_provenance else None,
                    "source_references": mudra_evidence.get("source_references", []) if has_source_provenance else [],
                    "uncertainty_notes": mudra_evidence.get("uncertainty_notes", []) if has_source_provenance else [],
                    "evidence_ids": [mudra_evidence["id"]] if mudra_evidence and mudra_evidence.get("id") else [],
                } if mudra_label else None,
                "bhava": {
                    "label": bhava_label,
                    "confidence": row.get("bhava_confidence"),
                    "evidence_ids": [bhava_evidence["id"]] if bhava_evidence and bhava_evidence.get("id") else [timeline_id],
                } if bhava_label else None,
                "pose": (
                    {
                        "pose_evidence": pose_event.get("pose_evidence"),
                        "movement_evidence": pose_event.get("movement_evidence"),
                        "confidence": pose_event.get("confidence"),
                        "evidence_ids": pose_event.get("evidence_ids", []),
                        "grounding_status": pose_event.get("grounding_status"),
                    }
                    if pose_event and pose_event.get("pose_evidence") is not None
                    else None
                ),
                "audio": None,
                "temporal_relation": {
                    "type": "after",
                    "event_id": events[-1]["event_id"],
                    "evidence_ids": [timeline_id, events[-1]["evidence_ids"][0]],
                } if events else None,
                "causal_relation": None,
                "evidence_ids": event_evidence_ids,
                "semantic_grounding_status": (
                    "source_backed_mudra_knowledge"
                    if mudra_label and mudra_status == "grounded" and has_source_provenance
                    else "mudra_observation"
                    if mudra_label
                    else "facial_expression_observation"
                ),
            }
        )

    return {
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "status": "completed",
        "events": events,
        "narrative_confidence": "medium" if events else "low",
        "unsupported_semantics": [
            "subject",
            "action",
            "object",
            "target",
            "location",
            "pose",
            "audio",
            "causal_relation",
        ],
    }


def save_semantic_events(analysis_id: str) -> dict[str, Any]:
    """Compose and persist the new artifact for exactly one analysis ID."""

    artifact = compose_semantic_events(analysis_id)
    save_modality_result(analysis_id, "semantic_events", artifact)
    return artifact