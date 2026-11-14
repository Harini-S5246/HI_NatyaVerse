"""Frame-level analysis API for detailed frame predictions."""
import logging
from collections import Counter
from pathlib import Path

from fastapi import APIRouter
import cv2

from app.config import settings
from app.core.errors import AppError
from app.services.result_service import get_modality_result, get_result
from app.utils.json_utils import load_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Frame Analysis"])
MIN_EVENT_PERSISTENCE = 2


def build_stable_events(frames: list[dict], modality: str) -> list[dict]:
    """Group labels while requiring a candidate change to persist."""
    if not frames:
        return []

    stable_label = frames[0][modality]["label"]
    stable_start = frames[0]
    stable_frames = [frames[0]]
    pending_label = None
    pending_frames: list[dict] = []
    events: list[dict] = []

    def append_event(event_frames: list[dict], label: str | None) -> None:
        if not event_frames:
            return
        confidences = [
            frame[modality]["confidence"]
            for frame in event_frames
            if frame[modality]["confidence"] is not None
        ]
        events.append({
            "modality": modality,
            "label": label,
            "start_timestamp": event_frames[0]["timestamp"],
            "end_timestamp": event_frames[-1]["timestamp"],
            "first_frame_number": event_frames[0]["frame_number"],
            "last_frame_number": event_frames[-1]["frame_number"],
            "representative_frame": event_frames[len(event_frames) // 2],
            "frame_count": len(event_frames),
            "average_confidence": sum(confidences) / len(confidences) if confidences else None,
        })

    for frame in frames[1:]:
        label = frame[modality]["label"]
        if label == stable_label:
            stable_frames.extend(pending_frames)
            pending_frames = []
            pending_label = None
            stable_frames.append(frame)
        elif label == pending_label:
            pending_frames.append(frame)
            if len(pending_frames) >= MIN_EVENT_PERSISTENCE:
                append_event(stable_frames, stable_label)
                stable_label = pending_label
                stable_frames = pending_frames
                pending_label = None
                pending_frames = []
        else:
            pending_label = label
            pending_frames = [frame]

    stable_frames.extend(pending_frames)
    append_event(stable_frames, stable_label)
    return events


def get_manifest_for_video(video_id: str) -> dict:
    """Load the frame manifest for a video."""
    video_frames_dir = settings.frame_output_dir / video_id
    manifest_path = video_frames_dir / "manifest.json"
    
    if not manifest_path.is_file():
        raise AppError("Frame manifest not found. Run frame extraction first.", 404, "MANIFEST_NOT_FOUND")
    
    return load_json(manifest_path)


def build_frame_level_analysis(video_id: str) -> dict:
    """
    Build frame-level analysis by combining:
    1. Extracted frame metadata (frame_number, timestamp, filename)
    2. Mudra predictions
    3. Bhava predictions
    4. Pose predictions (if available)
    
    Returns structure:
    {
      "video_id": "...",
      "status": "completed" | "partial" | "unavailable",
      "total_frames": 357,
      "frames": [
        {
          "frame_number": 0,
          "timestamp": 0.0,
          "filename": "frame_000000.jpg",
          "mudra": {"label": "Shivalinga", "confidence": 0.07, "status": "detected"},
          "bhava": {"label": "Angry", "confidence": 0.68, "status": "detected"},
          "pose": {"label": "...", "confidence": 0.0, "status": "unavailable"}
        }
      ]
    }
    """
    manifest = get_manifest_for_video(video_id)
    frames_data = manifest.get("frames", [])
    
    if not frames_data:
        raise AppError("No frames found in manifest.", 404, "NO_FRAMES")
    
    # Try to load modality results
    mudra_result = None
    bhava_result = None
    pose_result = None
    
    try:
        mudra_result = get_modality_result(video_id, "mudra")
    except AppError:
        logger.warning("Mudra result not available for video_id=%s", video_id)
    
    try:
        bhava_result = get_modality_result(video_id, "bhava")
    except AppError:
        logger.warning("Bhava result not available for video_id=%s", video_id)
    
    try:
        pose_result = get_modality_result(video_id, "pose")
    except AppError:
        logger.debug("Pose result not available for video_id=%s", video_id)
    
    # Build frame-level array by matching predictions with manifest
    frame_level = []
    
    for frame_info in frames_data:
        frame_number = frame_info.get("frame_number")
        timestamp = frame_info.get("timestamp")
        filename = frame_info.get("filename")
        
        # Find predictions for this frame
        mudra_pred = None
        if mudra_result:
            preds = mudra_result.get("frames", mudra_result.get("predictions", []))
            mudra_pred = next(
                (p for p in preds if p.get("frame_number") == frame_number),
                None
            )
        
        bhava_pred = None
        if bhava_result:
            preds = bhava_result.get("frames", bhava_result.get("predictions", []))
            bhava_pred = next(
                (p for p in preds if p.get("frame_number") == frame_number),
                None
            )
        
        pose_pred = None
        if pose_result:
            preds = pose_result.get("frames", pose_result.get("predictions", []))
            pose_pred = next(
                (p for p in preds if p.get("frame_number") == frame_number),
                None
            )

        source_references = mudra_pred.get("source_references") if mudra_pred else None
        verification_status = mudra_pred.get("verification_status") if mudra_pred else None
        knowledge_status = mudra_pred.get("knowledge_status") if mudra_pred else None
        uncertainty_notes = mudra_pred.get("uncertainty_notes") if mudra_pred else None
        mudra_meaning_is_source_backed = bool(
            mudra_pred
            and verification_status in {"verified", "partially_verified"}
            and knowledge_status == verification_status
            and isinstance(mudra_pred.get("claim_id"), str)
            and mudra_pred["claim_id"].strip()
            and isinstance(source_references, list)
            and source_references
            and all(isinstance(reference, str) and reference.strip() for reference in source_references)
            and isinstance(uncertainty_notes, list)
            and all(isinstance(note, str) for note in uncertainty_notes)
            and isinstance(mudra_pred.get("meaning"), str)
            and mudra_pred["meaning"].strip()
        )
        
        frame_entry = {
            "frame_number": frame_number,
            "timestamp": timestamp,
            "filename": filename,
            "frame_url": f"/api/videos/{video_id}/frames/{filename}",
            "mudra": {
                "label": mudra_pred.get("mudra") if mudra_pred else None,
                "confidence": mudra_pred.get("confidence") if mudra_pred else None,
                "status": mudra_pred.get("status", "detected") if mudra_pred else "unavailable",
                "meaning": mudra_pred.get("meaning") if mudra_meaning_is_source_backed else None,
                "verification_status": verification_status,
                "knowledge_status": knowledge_status,
                "claim_id": mudra_pred.get("claim_id") if mudra_pred and isinstance(mudra_pred.get("claim_id"), str) else None,
                "source_references": [
                    reference for reference in source_references
                    if isinstance(reference, str) and reference.strip()
                ] if isinstance(source_references, list) else [],
                "uncertainty_notes": uncertainty_notes if isinstance(uncertainty_notes, list) else [],
                "uncertainty_reason": (
                    mudra_pred.get("uncertainty_reason")
                    if mudra_pred and isinstance(mudra_pred.get("uncertainty_reason"), str)
                    else None
                ),
                "explanation": (
                    f"Knowledge-base meaning: {mudra_pred.get('verification_status').replace('_', ' ')}."
                    if mudra_meaning_is_source_backed
                    else "No source-backed knowledge-base meaning is available."
                    if mudra_pred
                    else None
                ),
            } if mudra_result else {"label": None, "confidence": None, "status": "unavailable"},
            "bhava": {
                "label": bhava_pred.get("bhava") if bhava_pred else None,
                "confidence": bhava_pred.get("confidence") if bhava_pred else None,
                "status": "detected" if bhava_pred else "unavailable",
            } if bhava_result else {"label": None, "confidence": None, "status": "unavailable"},
            "pose": {
                "label": pose_pred.get("label") if pose_pred else None,
                "confidence": pose_pred.get("confidence") if pose_pred else None,
                "status": "detected" if pose_pred else "unavailable",
            } if pose_result else {"label": None, "confidence": None, "status": "unavailable"},
        }
        
        frame_level.append(frame_entry)
    
    # Determine overall status
    status = "completed"
    if not mudra_result or not bhava_result:
        status = "partial"
    
    mudra_counts = Counter(frame["mudra"]["label"] for frame in frame_level if frame["mudra"]["label"])
    bhava_counts = Counter(frame["bhava"]["label"] for frame in frame_level if frame["bhava"]["label"])
    dominant_mudra = mudra_counts.most_common(1)[0] if mudra_counts else None
    dominant_bhava = bhava_counts.most_common(1)[0] if bhava_counts else None
    events = {
        "mudra": build_stable_events(frame_level, "mudra"),
        "bhava": build_stable_events(frame_level, "bhava"),
        "pose": build_stable_events(frame_level, "pose"),
    }

    return {
        "video_id": video_id,
        "status": status,
        "total_frames": len(frame_level),
        "frames": frame_level,
        "events": events,
        "event_persistence_frames": MIN_EVENT_PERSISTENCE,
        "occurrences": {
            "mudra": dict(mudra_counts),
            "bhava": dict(bhava_counts),
        },
        "warnings": {
            "mudra": (
                {
                    "type": "repetitive_predictions",
                    "message": "Mudra model shows highly repetitive predictions. This may indicate model bias/collapse.",
                    "dominant_label": dominant_mudra[0],
                    "dominant_frames": dominant_mudra[1],
                    "total_frames": len(frame_level),
                }
                if dominant_mudra and dominant_mudra[1] / len(frame_level) >= 0.9
                else None
            ),
            "bhava": (
                {
                    "type": "repetitive_predictions",
                    "message": "Bhava model shows highly repetitive predictions. This may indicate model bias/collapse.",
                    "dominant_label": dominant_bhava[0],
                    "dominant_frames": dominant_bhava[1],
                    "total_frames": len(frame_level),
                }
                if dominant_bhava and dominant_bhava[1] / len(frame_level) >= 0.9
                else None
            ),
        },
    }


@router.get("/videos/{video_id}/analysis/frames")
async def get_frame_level_analysis(video_id: str) -> dict:
    """
    Get frame-level analysis for a video.
    
    Returns frame-by-frame predictions for mudra, bhava, and pose.
    
    Args:
        video_id: The video identifier
        
    Returns:
        Frame-level analysis with predictions and metadata
        
    Raises:
        404: If frames or predictions not found
    """
    return build_frame_level_analysis(video_id)


@router.get("/videos/{video_id}/analysis/frames/summary")
async def get_frame_analysis_summary(video_id: str) -> dict:
    """
    Get a summary of frame-level analysis.
    
    Includes statistics like:
    - Total frames analyzed
    - Unique mudra classes
    - Unique bhava classes
    - Confidence ranges
    - Prediction distribution
    
    Args:
        video_id: The video identifier
        
    Returns:
        Summary statistics
    """
    analysis = build_frame_level_analysis(video_id)
    frames = analysis.get("frames", [])
    
    # Collect statistics
    mudra_labels = [f["mudra"]["label"] for f in frames if f["mudra"]["label"]]
    bhava_labels = [f["bhava"]["label"] for f in frames if f["bhava"]["label"]]
    mudra_confidences = [f["mudra"]["confidence"] for f in frames if f["mudra"]["confidence"] is not None]
    bhava_confidences = [f["bhava"]["confidence"] for f in frames if f["bhava"]["confidence"] is not None]
    
    return {
        "video_id": video_id,
        "total_frames": len(frames),
        "mudra": {
            "unique_classes": len(set(mudra_labels)),
            "unique_labels": sorted(set(mudra_labels)),
            "confidence_range": {
                "min": min(mudra_confidences) if mudra_confidences else None,
                "max": max(mudra_confidences) if mudra_confidences else None,
                "mean": sum(mudra_confidences) / len(mudra_confidences) if mudra_confidences else None,
            },
            "label_counts": {label: mudra_labels.count(label) for label in set(mudra_labels)},
        },
        "bhava": {
            "unique_classes": len(set(bhava_labels)),
            "unique_labels": sorted(set(bhava_labels)),
            "confidence_range": {
                "min": min(bhava_confidences) if bhava_confidences else None,
                "max": max(bhava_confidences) if bhava_confidences else None,
                "mean": sum(bhava_confidences) / len(bhava_confidences) if bhava_confidences else None,
            },
            "label_counts": {label: bhava_labels.count(label) for label in set(bhava_labels)},
        },
    }


@router.get("/videos/{video_id}/analysis/frames/segments")
async def get_frame_segments(video_id: str) -> dict:
    """
    Get time-based segments where consecutive frames have the same predictions.
    
    Returns:
        Grouped segments with start/end times and predictions
    """
    analysis = build_frame_level_analysis(video_id)
    frames = analysis.get("frames", [])
    
    if not frames:
        return {"video_id": video_id, "segments": []}
    
    # Group consecutive frames with same mudra+bhava prediction
    segments = []
    current_segment = None
    
    for frame in frames:
        mudra_label = frame["mudra"]["label"]
        bhava_label = frame["bhava"]["label"]
        
        # Check if this frame belongs to the current segment
        if (current_segment and 
            current_segment["mudra"] == mudra_label and 
            current_segment["bhava"] == bhava_label):
            # Continue the segment
            current_segment["end_timestamp"] = frame["timestamp"]
            current_segment["frame_count"] += 1
            current_segment["last_frame_number"] = frame["frame_number"]
        else:
            # Start a new segment
            if current_segment:
                segments.append(current_segment)
            
            current_segment = {
                "mudra": mudra_label,
                "mudra_confidence": frame["mudra"]["confidence"],
                "bhava": bhava_label,
                "bhava_confidence": frame["bhava"]["confidence"],
                "start_timestamp": frame["timestamp"],
                "end_timestamp": frame["timestamp"],
                "first_frame_number": frame["frame_number"],
                "last_frame_number": frame["frame_number"],
                "frame_count": 1,
            }
    
    # Don't forget the last segment
    if current_segment:
        segments.append(current_segment)
    
    return {
        "video_id": video_id,
        "segment_count": len(segments),
        "segments": segments,
    }
