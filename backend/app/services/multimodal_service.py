from __future__ import annotations
from collections import Counter

from app.services.knowledge_service import build_evidence


def build_result(analysis_id: str, metadata: dict, timeline: list[dict]) -> dict:
    """Fuse aligned per-frame outputs without adding unobserved claims.

    The returned result carries a structured ``evidence`` object (grounded /
    detected / unresolved / interpreted) that the frontend contract expects.
    A mudra is grounded only when the curated knowledge base has a matching
    entry; everything else stays explicitly unresolved or detected.
    """
    def dominant(key: str):
        labels = [entry[key]["label"] for entry in timeline if entry.get(key, {}).get("label")]
        return Counter(labels).most_common(1)[0][0] if labels else None

    # Aggregate per-label detections from the timeline.
    detections: list[dict] = []
    seen: set[str] = set()
    for entry in timeline:
        item = entry.get("mudra", {})
        label = item.get("label")
        if not label or label in seen:
            continue
        seen.add(label)
        detections.append({
            "name": label,
            "confidence": item.get("confidence"),
            "grounded": False,
            "status": "detected",
            "timestamps": [entry["timestamp_sec"]],
        })

    result = {
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "status": "completed",
        "performance": {
            "duration_seconds": metadata["duration_seconds"],
            "performance_name": metadata.get("original_filename"),
        },
        "timeline": timeline,
        "mudra": {"detections": detections},
        "bhava": {"dominant_emotion": dominant("bhava")},
        "pose": {"primary_pose": dominant("pose")},
        "dance_events": [],
        "story": {"status": "not_generated"},
        "metadata": metadata,
    }

    # Attach the evidence object assembled from the curated knowledge base.
    result["evidence"] = build_evidence(result)
    return result