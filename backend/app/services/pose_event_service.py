"""Phase 2 Pose evidence artifact boundary.

The current repository has no compatible landmark extractor or saved Pose
result. This service records that limitation explicitly and never invents
movement labels from Mudra, Bhava, or Pose class names.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.services.result_service import get_modality_result, save_modality_result


def compose_pose_events(analysis_id: str) -> dict[str, Any]:
    """Create a Pose evidence artifact with unknown movement evidence."""

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

    events = []
    for index, row in enumerate(fusion.get("timeline", []) or [], start=1):
        if not isinstance(row, dict):
            continue
        timeline_id = f"fusion-timeline-{index:04d}"
        events.append(
            {
                "event_id": f"pose_event_{index:04d}",
                "analysis_id": analysis_id,
                "video_id": analysis_id,
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "pose_evidence": None,
                "movement_evidence": None,
                "confidence": None,
                "evidence_ids": [timeline_id],
                "grounding_status": "unavailable",
            }
        )

    return {
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "status": "unavailable",
        "availability": "insufficient_pose_evidence",
        "message": (
            "No compatible pose-landmark extraction result is available. "
            "Movement evidence remains unknown."
        ),
        "events": events,
        "supported_event_count": 0,
        "unknown_event_count": len(events),
    }


def save_pose_events(analysis_id: str) -> dict[str, Any]:
    """Compose and persist Pose evidence for exactly one analysis ID."""

    artifact = compose_pose_events(analysis_id)
    save_modality_result(analysis_id, "pose_events", artifact)
    return artifact