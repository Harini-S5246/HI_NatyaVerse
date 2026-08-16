"""Multimodal fusion and evidence consolidation.

This service combines the already-computed Mudra and Bhava modality results
for the same ``video_id`` into ONE canonical analysis result.  It is an
evidence-consolidation layer, NOT an interpretation layer — it never invents
relationships between modalities and never generates narrative text.

* Loads the stored Mudra and Bhava modality results (no re-inference).
* Aligns their temporal events by timestamp intervals into a unified timeline.
* Preserves Mudra grounding / unresolved status and Bhava detected evidence.
* Produces a multimodal summary without claiming a specific Mudra expresses
  a specific Bhava unless the knowledge base says so (it currently does not,
  so no such claim is ever generated).
"""
from __future__ import annotations

from app.core.errors import AppError
from app.services.result_service import (
    get_modality_result,
    save_modality_result,
    save_result,
)


def _active_event(events: list[dict], time: float) -> dict | None:
    """Return the event active at ``time``.

    Events are inclusive-end segments; at a boundary instant (where one event
    ends and the next begins) the event that STARTS there begins the new
    segment, so it is preferred.  Otherwise the first covering event wins.
    """
    for event in events:
        if event["start_time"] == time:
            return event
    for event in events:
        if event["start_time"] <= time <= event["end_time"]:
            return event
    return None


def _mudra_detection_lookup(mudra_result: dict) -> dict[str, dict]:
    """Build label -> detection map for the stored Mudra result."""
    lookup: dict[str, dict] = {}
    for detection in mudra_result.get("mudra", {}).get("detections", []):
        label = detection.get("name")
        if label:
            lookup[label] = detection
    return lookup


def _build_timeline(
    mudra_events: list[dict],
    bhava_events: list[dict],
    mudra_detections: dict[str, dict],
) -> list[dict]:
    """Align Mudra and Bhava events by time into one canonical timeline.

    Each output row is one contiguous time window during which the active
    Mudra and Bhava combination is constant.  Rows that contain neither a
    Mudra nor a Bhava event are omitted.
    """
    breakpoints = sorted(
        {
            event["start_time"]
            for event in (*mudra_events, *bhava_events)
        }
        | {
            event["end_time"]
            for event in (*mudra_events, *bhava_events)
        }
    )

    timeline: list[dict] = []
    for start, end in zip(breakpoints, breakpoints[1:]):
        if end <= start:
            continue
        mudra_event = _active_event(mudra_events, start)
        bhava_event = _active_event(bhava_events, start)
        if mudra_event is None and bhava_event is None:
            continue

        mudra_label = mudra_event["mudra"] if mudra_event else None
        mudra_conf = mudra_event["confidence"] if mudra_event else None
        mudra_det = mudra_detections.get(mudra_label, {}) if mudra_label else {}
        bhava_label = bhava_event["bhava"] if bhava_event else None
        bhava_conf = bhava_event["confidence"] if bhava_event else None

        row = {
            "start_time": round(start, 6),
            "end_time": round(end, 6),
            "mudra": mudra_label,
            "mudra_confidence": mudra_conf,
            "mudra_grounded": bool(mudra_det.get("grounded", False)) if mudra_label else False,
            "bhava": bhava_label,
            "bhava_confidence": bhava_conf,
        }

        # Merge with the previous row when the modality combination is identical.
        if timeline and _same_combination(timeline[-1], row):
            timeline[-1]["end_time"] = row["end_time"]
        else:
            timeline.append(row)

    return timeline


def _same_combination(a: dict, b: dict) -> bool:
    return (
        a.get("mudra") == b.get("mudra")
        and a.get("bhava") == b.get("bhava")
    )


def _consolidate_evidence(mudra_result: dict, bhava_result: dict) -> dict[str, list[dict]]:
    """Consolidate the four-part evidence from both stored modality results.

    The evidence from the Mudra result (grounded / unresolved mudras) and the
    evidence from the Bhava result (detected bhava) are combined without
    re-deriving or inventing relationships.
    """
    consolidated: dict[str, list[dict]] = {
        "grounded": [],
        "detected": [],
        "unresolved": [],
        "interpreted": [],
    }
    seen_ids: set[str] = set()

    for result in (mudra_result, bhava_result):
        for category in consolidated:
            for item in result.get("evidence", {}).get(category, []):
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id in seen_ids:
                    continue
                if item_id is not None:
                    seen_ids.add(item_id)
                consolidated[category].append(item)

    return consolidated


def fuse_video(video_id: str) -> dict:
    """Fuse the stored Mudra and Bhava results for one video into a canonical result."""
    try:
        mudra_result = get_modality_result(video_id, "mudra")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            raise AppError(
                "Mudra result was not found for this video. Run the Mudra analysis first.",
                404,
                "MUDRA_RESULT_REQUIRED",
            ) from exc
        raise

    try:
        bhava_result = get_modality_result(video_id, "bhava")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            raise AppError(
                "Bhava result was not found for this video. Run the Bhava analysis first.",
                404,
                "BHAVA_RESULT_REQUIRED",
            ) from exc
        raise

    mudra_events = mudra_result.get("mudra_events", [])
    bhava_events = bhava_result.get("bhava_events", [])
    mudra_detections = _mudra_detection_lookup(mudra_result)

    timeline = _build_timeline(mudra_events, bhava_events, mudra_detections)

    # Summary — averages come from each modality's own summary (no cross-claims).
    mudra_summary = mudra_result.get("summary", {})
    bhava_summary = bhava_result.get("summary", {})
    frame_count = mudra_result.get("frame_count") or bhava_result.get("frame_count") or 0

    fused_summary = {
        "dominant_mudra": mudra_summary.get("dominant_mudra"),
        "dominant_bhava": bhava_summary.get("dominant_bhava"),
        "mudra_event_count": len(mudra_events),
        "bhava_event_count": len(bhava_events),
        "average_mudra_confidence": mudra_summary.get("average_confidence"),
        "average_bhava_confidence": bhava_summary.get("average_confidence"),
        "frame_count": frame_count,
    }

    result = {
        "analysis_id": video_id,
        "video_id": video_id,
        "status": "completed",
        "timeline": timeline,
        "summary": fused_summary,
    }

    # Evidence consolidation (preserves grounding, unresolved, detected; no invention).
    result["evidence"] = _consolidate_evidence(mudra_result, bhava_result)

    save_result(result)
    save_modality_result(video_id, "fusion", result)
    return result