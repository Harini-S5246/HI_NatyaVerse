from __future__ import annotations

import math

LOW_CONFIDENCE_THRESHOLD = 0.5


def _as_float(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalise_mudra_segment(segment: dict) -> dict | None:
    if not isinstance(segment, dict):
        return None

    label = segment.get("mudra_label")
    if label is None:
        label = segment.get("mudra")
    if not isinstance(label, str) or not label.strip():
        return None

    has_start = "start_timestamp" in segment or "start_time" in segment
    has_end = "end_timestamp" in segment or "end_time" in segment
    start = _as_float(segment.get("start_timestamp", segment.get("start_time")))
    end = _as_float(segment.get("end_timestamp", segment.get("end_time")))
    if has_start and start is None:
        return None
    if has_end and end is None:
        return None
    if start is None and end is not None:
        start = end
    if end is None and start is not None:
        end = start
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start

    confidence = _as_float(segment.get("confidence"))
    if confidence is None:
        confidence = _as_float(segment.get("mean_confidence"))
    if confidence is None:
        confidence = _as_float(segment.get("mudra_confidence"))

    segment_id = segment.get("segment_id") or segment.get("id")
    return {
        "segment_id": segment_id,
        "mudra_label": label.strip(),
        "start_timestamp": float(start),
        "end_timestamp": float(end),
        "confidence": confidence,
        "frame_indices": segment.get("frame_indices") if isinstance(segment.get("frame_indices"), list) else [],
        "supporting_evidence_ids": segment.get("supporting_evidence_ids") if isinstance(segment.get("supporting_evidence_ids"), list) else [],
        "status": segment.get("status") or "valid",
    }


def _normalise_expression_observation(observation: dict) -> dict | None:
    if not isinstance(observation, dict):
        return None

    label = observation.get("bhava")
    if label is None:
        label = observation.get("label")
    if label is None:
        label = observation.get("name")
    if not isinstance(label, str) or not label.strip():
        return None

    point_timestamp = _as_float(observation.get("timestamp"))
    has_start = "start_timestamp" in observation or "start_time" in observation or "start" in observation
    has_end = "end_timestamp" in observation or "end_time" in observation or "end" in observation
    start = _as_float(observation.get("start_timestamp", observation.get("start_time", observation.get("start"))))
    end = _as_float(observation.get("end_timestamp", observation.get("end_time", observation.get("end"))))
    if has_start and start is None:
        return None
    if has_end and end is None:
        return None
    if start is None and end is not None:
        start = end
    if end is None and start is not None:
        end = start
    if point_timestamp is not None and (start is None or end is None):
        start = point_timestamp
        end = point_timestamp
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start

    confidence = _as_float(observation.get("confidence"))
    if confidence is None:
        confidence = _as_float(observation.get("expression_confidence"))

    frame_number = observation.get("frame_number")
    if frame_number is not None:
        try:
            frame_number = int(frame_number)
        except (TypeError, ValueError):
            frame_number = None

    return {
        "label": label.strip(),
        "start_timestamp": float(start),
        "end_timestamp": float(end),
        "confidence": confidence,
        "frame_number": frame_number,
        "source_timestamp": point_timestamp,
        "filename": observation.get("filename"),
        "status": observation.get("status") or "valid",
    }


def calculate_temporal_overlap(start_a: float | None, end_a: float | None, start_b: float | None, end_b: float | None) -> float:
    if start_a is None or end_a is None or start_b is None or end_b is None:
        return 0.0
    if start_a > end_a:
        start_a, end_a = end_a, start_a
    if start_b > end_b:
        start_b, end_b = end_b, start_b
    overlap_start = max(start_a, start_b)
    overlap_end = min(end_a, end_b)
    if overlap_end < overlap_start:
        return 0.0
    return float(overlap_end - overlap_start)


def calculate_alignment_confidence(mudra_confidence: float | None, expression_confidence: float | None, *, overlap_duration: float, mudra_duration: float, coverage_ratio: float) -> float:
    mudra_confidence = mudra_confidence if mudra_confidence is not None else 0.0
    expression_confidence = expression_confidence if expression_confidence is not None else 0.0
    if mudra_duration <= 0:
        coverage = 0.0 if coverage_ratio <= 0 else 1.0
    else:
        coverage = min(1.0, max(0.0, coverage_ratio))
    if overlap_duration <= 0 and coverage <= 0:
        return 0.0
    # This is intentionally not a blind average: temporal coverage is included and
    # the Mudra confidence is weighted more heavily because the mutation is
    # segment-level evidence from the Mudra service.
    weighted = (0.6 * mudra_confidence) + (0.4 * expression_confidence)
    return round(max(0.0, min(1.0, weighted * coverage)), 6)


def validate_alignment_boundaries(mudra_segment: dict | None, expression_observations: list[dict]) -> tuple[bool, str]:
    if not isinstance(mudra_segment, dict):
        return False, "insufficient_temporal_evidence"
    if mudra_segment.get("start_timestamp") is None or mudra_segment.get("end_timestamp") is None:
        return False, "insufficient_temporal_evidence"
    if not expression_observations:
        return True, "no_expression_observation"
    return True, "valid"


def _coerce_expression_list(bhava_result: dict | None) -> list[dict]:
    if not isinstance(bhava_result, dict):
        return []

    exploded: list[dict] = []
    seen: set[tuple[str, float, float, float | None]] = set()
    for source in (
        bhava_result.get("frames", []),
        bhava_result.get("bhava", {}).get("detections", []),
        bhava_result.get("bhava", {}).get("segments", []),
        bhava_result.get("bhava_events", []),
    ):
        if not isinstance(source, list):
            continue
        for item in source:
            normalized = _normalise_expression_observation(item)
            if normalized is None:
                continue
            key = (
                normalized["label"],
                normalized["start_timestamp"],
                normalized["end_timestamp"],
                normalized["confidence"],
            )
            if key in seen:
                continue
            seen.add(key)
            exploded.append(normalized)
    return sorted(
        exploded,
        key=lambda item: (
            item["start_timestamp"],
            item["end_timestamp"],
            item["frame_number"] if item["frame_number"] is not None else -1,
        ),
    )


def _coerce_mudra_segments(mudra_result: dict | None) -> list[dict]:
    if not isinstance(mudra_result, dict):
        return []

    segments: list[dict] = []
    temporal = mudra_result.get("temporal_sequence")
    if isinstance(temporal, dict):
        for segment in temporal.get("segments", []):
            normalized = _normalise_mudra_segment(segment)
            if normalized is not None:
                segments.append(normalized)
        if segments:
            return segments

    for event in mudra_result.get("mudra_events", []):
        normalized = _normalise_mudra_segment(event)
        if normalized is not None:
            segments.append(normalized)
    return segments


def summarize_expression_alignment(mudra_segment: dict, expression_observations: list[dict]) -> dict:
    mudra_start = mudra_segment["start_timestamp"]
    mudra_end = mudra_segment["end_timestamp"]
    mudra_duration = max(0.0, mudra_end - mudra_start)

    point_matches: list[dict] = []
    interval_matches: list[dict] = []
    for observation in expression_observations:
        obs_start = observation["start_timestamp"]
        obs_end = observation["end_timestamp"]
        if obs_start == obs_end:
            if mudra_start <= obs_start <= mudra_end:
                point_matches.append(observation)
            continue

        if obs_end < mudra_start or obs_start > mudra_end:
            continue
        interval_matches.append(observation)

    matched_observations = sorted(
        (*point_matches, *interval_matches),
        key=lambda item: (
            item["start_timestamp"],
            item["end_timestamp"],
            item["frame_number"] if item["frame_number"] is not None else -1,
        ),
    )
    if not matched_observations:
        return {
            "expression_observations": [],
            "expression_labels": [],
            "expression_confidences": [],
            "overlap_duration": 0.0,
            "mudra_coverage_ratio": 0.0,
            "alignment_status": "no_expression_observation",
            "uncertainty_status": "missing_modality",
            "alignment_method": "interval_overlap",
            "alignment_confidence": 0.0,
        }

    overlap_ranges: list[tuple[float, float]] = []
    for observation in interval_matches:
        overlap_start = max(mudra_start, observation["start_timestamp"])
        overlap_end = min(mudra_end, observation["end_timestamp"])
        if overlap_end > overlap_start:
            overlap_ranges.append((overlap_start, overlap_end))

    merged_ranges: list[tuple[float, float]] = []
    for start, end in sorted(overlap_ranges):
        if not merged_ranges or start > merged_ranges[-1][1]:
            merged_ranges.append((start, end))
            continue
        prev_start, prev_end = merged_ranges[-1]
        merged_ranges[-1] = (prev_start, max(prev_end, end))

    overlap_duration = sum(end - start for start, end in merged_ranges)
    if mudra_duration > 0:
        coverage_ratio = min(1.0, overlap_duration / mudra_duration) if interval_matches else 0.0
    else:
        coverage_ratio = 0.0

    if interval_matches and coverage_ratio >= 0.5:
        alignment_status = "aligned"
    elif matched_observations:
        alignment_status = "partial_overlap"
    else:
        alignment_status = "no_expression_observation"

    expr_confidences = [obs["confidence"] for obs in matched_observations if obs["confidence"] is not None]
    expression_confidence = sum(expr_confidences) / len(expr_confidences) if expr_confidences else None
    mudra_confidence = mudra_segment.get("confidence")
    alignment_confidence = calculate_alignment_confidence(
        mudra_confidence,
        expression_confidence,
        overlap_duration=overlap_duration,
        mudra_duration=mudra_duration,
        coverage_ratio=coverage_ratio,
    )

    uncertainty_status = "normal"
    if not matched_observations:
        uncertainty_status = "missing_modality"
    elif (mudra_confidence is not None and mudra_confidence < LOW_CONFIDENCE_THRESHOLD) or (expression_confidence is not None and expression_confidence < LOW_CONFIDENCE_THRESHOLD):
        uncertainty_status = "low_confidence"
    elif not interval_matches and point_matches:
        uncertainty_status = "insufficient_evidence"

    normalized_observations = []
    for obs in matched_observations:
        normalized_observations.append({
            "label": obs["label"],
            "strategy": "point_timestamp_match" if obs["start_timestamp"] == obs["end_timestamp"] else "interval_overlap",
            "start_timestamp": obs["start_timestamp"],
            "end_timestamp": obs["end_timestamp"],
            "confidence": obs["confidence"],
            "frame_number": obs["frame_number"],
            "filename": obs["filename"],
        })

    return {
        "expression_observations": normalized_observations,
        "expression_labels": [obs["label"] for obs in matched_observations],
        "expression_confidences": [obs["confidence"] for obs in matched_observations],
        "overlap_duration": round(overlap_duration, 6),
        "mudra_coverage_ratio": round(coverage_ratio, 6),
        "alignment_status": alignment_status,
        "uncertainty_status": uncertainty_status,
        "alignment_method": "interval_overlap" if interval_matches else "point_timestamp_match",
        "alignment_confidence": alignment_confidence,
        "point_match_count": len(point_matches),
    }


def align_mudra_bhava_sequences(mudra_result: dict | None, bhava_result: dict | None, *, video_id: str | None = None, analysis_id: str | None = None) -> dict:
    """Align Mudra segments against Bhava observations while preserving original model outputs."""
    mudra_segments = _coerce_mudra_segments(mudra_result)
    expression_observations = _coerce_expression_list(bhava_result)
    if not mudra_segments:
        return {
            "video_id": video_id,
            "analysis_id": analysis_id,
            "alignment_id": f"{analysis_id or video_id or 'mudra-bhava'}-alignment",
            "alignments": [],
            "summary": {
                "total_mudra_segments": 0,
                "total_expression_observations": len(expression_observations),
                "aligned_segments": 0,
                "partial_overlap_segments": 0,
                "no_expression_observation_segments": 0,
            },
            "status": "completed",
        }

    alignments: list[dict] = []
    for segment in mudra_segments:
        segment_id = segment.get("segment_id") or f"{analysis_id or video_id or 'mudra'}-segment-{len(alignments) + 1}"
        matched_observations = []
        for observation in expression_observations:
            obs_start = observation["start_timestamp"]
            obs_end = observation["end_timestamp"]
            segment_start = segment["start_timestamp"]
            segment_end = segment["end_timestamp"]
            if obs_end < segment_start or obs_start > segment_end:
                continue
            if obs_start == obs_end == segment_start == segment_end:
                matched_observations.append(observation)
                continue
            matched_observations.append(observation)

        if not matched_observations:
            aligned_result = {
                "video_id": video_id,
                "analysis_id": analysis_id,
                "alignment_id": f"{analysis_id or video_id or 'mudra-bhava'}-alignment-{segment_id}",
                "mudra_segment_id": segment_id,
                "mudra_label": segment["mudra_label"],
                "mudra_start_timestamp": segment["start_timestamp"],
                "mudra_end_timestamp": segment["end_timestamp"],
                "mudra_confidence": segment.get("confidence"),
                "expression_observations": [],
                "expression_labels": [],
                "expression_confidences": [],
                "overlap_duration": 0.0,
                "mudra_coverage_ratio": 0.0,
                "alignment_status": "no_expression_observation",
                "uncertainty_status": "missing_modality",
                "alignment_method": "point_timestamp_match" if segment["start_timestamp"] == segment["end_timestamp"] else "interval_overlap",
                "alignment_confidence": 0.0,
                "point_match_count": 0,
            }
            alignments.append(aligned_result)
            continue

        summary = summarize_expression_alignment(segment, matched_observations)
        item = {
            "video_id": video_id,
            "analysis_id": analysis_id,
            "alignment_id": f"{analysis_id or video_id or 'mudra-bhava'}-alignment-{segment_id}",
            "mudra_segment_id": segment_id,
            "mudra_label": segment["mudra_label"],
            "mudra_start_timestamp": segment["start_timestamp"],
            "mudra_end_timestamp": segment["end_timestamp"],
            "mudra_confidence": segment.get("confidence"),
            "expression_observations": summary["expression_observations"],
            "expression_labels": summary["expression_labels"],
            "expression_confidences": summary["expression_confidences"],
            "overlap_duration": summary["overlap_duration"],
            "mudra_coverage_ratio": summary["mudra_coverage_ratio"],
            "alignment_status": summary["alignment_status"],
            "uncertainty_status": summary["uncertainty_status"],
            "alignment_method": summary["alignment_method"],
            "alignment_confidence": summary["alignment_confidence"],
            "point_match_count": summary.get("point_match_count", 0),
        }
        alignments.append(item)

    summary = {
        "total_mudra_segments": len(mudra_segments),
        "total_expression_observations": len(expression_observations),
        "aligned_segments": sum(1 for item in alignments if item["alignment_status"] == "aligned"),
        "partial_overlap_segments": sum(1 for item in alignments if item["alignment_status"] == "partial_overlap"),
        "no_expression_observation_segments": sum(1 for item in alignments if item["alignment_status"] == "no_expression_observation"),
        "insufficient_evidence_segments": sum(1 for item in alignments if item["uncertainty_status"] == "insufficient_evidence"),
    }
    return {
        "video_id": video_id,
        "analysis_id": analysis_id,
        "alignment_id": f"{analysis_id or video_id or 'mudra-bhava'}-alignment",
        "alignments": alignments,
        "summary": summary,
        "status": "completed",
    }
