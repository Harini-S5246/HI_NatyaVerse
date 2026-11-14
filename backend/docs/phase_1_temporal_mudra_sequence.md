# Phase 1 – Temporal Mudra Sequence Analysis

## Existing functionality reviewed

The project already had a temporal grouping routine in `backend/app/services/mudra_service.py` named `group_mudra_events`. Its behavior was intentionally conservative:

- iterate the prediction list in chronological order
- merge adjacent predictions when the mudra label is identical
- extend the segment `end_time`
- increment `frame_count`
- average the confidence values for that segment
- preserve a single aggregated confidence for the merged segment

This was useful for reducing frame-level noise into gesture-like clusters, but it only represented a simple run-length grouping of identical labels.

## Exact limitations of the original algorithm

The original grouping logic did not handle several Paper 2 requirements:

1. It tracked only mudra label equality; it did not preserve frame indices or supporting evidence references.
2. It did not create a structured temporal sequence object with segment IDs, previous/next segments, or transition metadata.
3. It did not detect transitions between different mudra segments in a structured way.
4. It did not identify repeated consecutive mudra patterns.
5. It did not document how to handle missing frames, invalid timestamps, or missing hand-detection states.
6. It did not distinguish low-confidence observations from confident predictions in the sequence structure.
7. It could not separate segments across long gaps because it only grouped by immediate label equality, with no explicit gap rule.

## Enhancement implemented in Phase 1

This phase keeps the legacy `group_mudra_events` behavior intact for compatibility and adds a separate structured temporal sequence builder that is attached to the existing mudra classification response as `temporal_sequence`.

The enhancement reuses the current frame-level mudra predictions and adds:

- segment IDs
- start and end timestamps
- duration calculations
- frame index lists
- supporting evidence IDs
- transition metadata for label changes
- repeated consecutive pattern detection
- explicit uncertainty tracking for low-confidence segments
- gap-aware segmentation to avoid joining unrelated segments across long missing intervals

The new sequence builder intentionally does not invent mudra labels or cultural meanings. It only describes what the model actually observed and preserves uncertainty when the confidence is low or the observation is missing.

## Segmentation rules

The temporal sequence follows these rules:

1. Valid predictions are those with a non-empty mudra label and a finite, non-negative timestamp.
2. Predictions with empty mudra labels, invalid timestamps, or missing-hand-detection markers are excluded from segment construction.
3. A new segment starts when the mudra label changes or when the gap between consecutive valid timestamps exceeds the configured `max_gap_seconds` threshold.
4. Consecutive identical and valid predictions are merged into one segment.
5. Segment confidence is preserved as mean/min/max values; the confidence is not silently converted into a verified label.
6. Repeated patterns are detected only for repeated consecutive mudra sequences, such as `[Pataka, Mayura, Pataka, Mayura]`, and are reported without interpretation.
7. A segment is marked as `low_confidence` when its mean confidence falls below the threshold of 0.5.

## Output structure (Phase 1)

The structured sequence is included alongside the legacy mudra result payload as:

```python
response["temporal_sequence"] = {
    "video_id": ...,
    "analysis_id": ...,
    "sequence_id": ...,
    "segments": [
        {
            "segment_id": ...,
            "mudra_label": ...,
            "start_timestamp": ...,
            "end_timestamp": ...,
            "duration": ...,
            "frame_indices": [...],
            "supporting_evidence_ids": [...],
            "confidence": {
                "mean": ...,
                "min": ...,
                "max": ...,
                "source": "model_prediction",
                "low_confidence": ...
            },
            "previous_segment": ...,
            "next_segment": ...,
            "transition": {...} or None,
            "repeated_pattern": {...} or None,
            "uncertainty_status": "normal" | "low_confidence"
        }
    ],
    "transitions": [...],
    "repeated_patterns": [...],
    "uncertainty_summary": {...}
}
```

This preserves the existing response contract while exposing a richer temporal representation for downstream Paper 2 features.

## Input and output example

Input prediction stream:

```python
[
    {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.92},
    {"mudra": "Pataka", "timestamp": 1.0, "frame_number": 1, "confidence": 0.88},
    {"mudra": "Mayura", "timestamp": 2.0, "frame_number": 2, "confidence": 0.71},
    {"mudra": "Mayura", "timestamp": 3.0, "frame_number": 3, "confidence": 0.69},
]
```

Segmented output:

```python
{
  "segments": [
    {"mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 1.0, "duration": 1.0},
    {"mudra_label": "Mayura", "start_timestamp": 2.0, "end_timestamp": 3.0, "duration": 1.0}
  ],
  "transitions": [{"previous_mudra": "Pataka", "next_mudra": "Mayura"}],
  "repeated_patterns": []
}
```

## Test coverage added in Phase 1

The following scenarios are now covered in `backend/tests/test_mudra_service.py`:

- consecutive identical mudras
- different mudra transitions
- repeated pattern detection
- low-confidence predictions
- missing predictions
- invalid timestamps and empty input
- timestamp ordering and gap handling
- duration calculation
- video_id and analysis_id isolation

## Actual validation results

Execution command:

```bash
cd C:\Users\selva\HI_NatyaVerse
pytest backend/tests/test_mudra_service.py backend/tests/test_fusion_service.py backend/tests/test_story_service.py -q
```

Actual result:

- 55 passed in 2.82s

## Scope and limitations

This is intentionally a minimal Phase 1 extension. It does not alter the underlying Mudra model weights, training pipeline, Story generation flow, knowledge base, or unrelated UI pages. It also does not claim that a low-confidence or repeated pattern has a cultural meaning on its own. Those interpretations remain for later Paper 2 phases.
