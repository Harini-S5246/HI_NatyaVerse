# Phase 2 – Mudra–Bhava Temporal Alignment

## Research objective

Phase 2 extends the Phase 1 temporal mudra sequence by aligning Mudra segments with the existing Bhava (facial-expression) predictions over time. The objective is not cultural interpretation; it is an evidence-based temporal association layer that makes explicit where the two streams overlap, where they are missing, and how uncertain the alignment is.

## Existing implementation reused

This phase intentionally reuses the architecture already in place:

- `backend/app/services/mudra_service.py`
  - existing mudra classification and Phase 1 temporal sequence builder
  - legacy `group_mudra_events` remains intact
- `backend/app/services/bhava_service.py`
  - existing Bhava frame predictions and temporal event grouping
- `backend/app/services/fusion_service.py`
  - existing fusion and timeline consolidation layer
- `backend/app/services/result_service.py`
  - saved modality results and persisted analysis records
- `backend/app/api/schemas/` and `backend/app/api/routes/`
  - existing response contracts and routing conventions

The new alignment logic is implemented as a focused service and attached to the existing fusion result structure rather than duplicating any separate application flow.

## New alignment architecture

The new service is:

- `backend/app/services/mudra_bhava_alignment_service.py`

It exposes structured functions for:

- `align_mudra_bhava_sequences()`
- `calculate_temporal_overlap()`
- `summarize_expression_alignment()`
- `calculate_alignment_confidence()`
- `validate_alignment_boundaries()`

The service normalizes:

- Mudra segments from the Phase 1 sequence (`temporal_sequence.segments`) or fallback legacy Mudra events
- Bhava observations from `frames`, `bhava_events`, `bhava.detections`, or `bhava.segments`

It preserves the original labels and confidence values from the model outputs and does not rename generic FER labels such as Happy, Sad, Angry, Neutral, Surprise, Fear, or Disgust into a classical Bhava label.

## Temporal overlap algorithm

For each Mudra segment, the service performs the following:

1. Reads the interval of the Mudra segment as `[mudra_start, mudra_end]`.
2. Collects Bhava observations whose intervals overlap the segment window or whose point timestamps fall within it.
3. Computes overlap duration using the actual interval intersection.
4. Calculates the Mudra coverage ratio as:

   coverage_ratio = overlap_duration / mudra_duration

   when the Mudra segment has a positive duration.

5. For interval coverage calculations, point observations contribute only to
   `point_match_count`. They may still appear in matched-observation details
   and identify a point match, but do not contribute to `overlap_duration` or
   `mudra_coverage_ratio`; their timestamps never create synthetic intervals.
   If there are no expression intervals, `alignment_method` is reported as
   `point_timestamp_match`.

Coverage is calculated only from genuine expression intervals. The intersecting
interval windows are clipped to the Mudra segment and overlapping windows are
merged before their durations are summed, so overlapping observations are never
double-counted.

This keeps the method evidence-based and transparent.

The implementation intentionally distinguishes three separate concepts:

- interval overlap: real temporal intersection between two valid intervals
- point match: a single timestamp observation that falls inside the Mudra segment
- interval coverage ratio: actual interval_overlap / mudra_duration, bounded to [0, 1]

Point matches are tracked separately via `point_match_count` and never converted into interval coverage. The persisted modality results normally use the video ID as the analysis ID; when both modalities carry a distinct matching analysis ID, fusion and alignment preserve it. Missing analysis IDs follow the existing convention and fall back to the requested video ID. Fusion rejects a stored video ID that differs from the request with `VIDEO_ID_MISMATCH`, and rejects modalities whose effective analysis IDs differ with `ANALYSIS_ID_MISMATCH` (both are HTTP 409 errors).

## Confidence and uncertainty handling

The alignment service keeps the original Mudra and Bhava confidences separate. It does not silently average them without a defined weighting rule.

The alignment confidence is defined as:

alignment_confidence = weighted_confidence * coverage_ratio

where:

weighted_confidence = (0.6 * mudra_confidence) + (0.4 * expression_confidence)

The weighting intentionally prioritizes the Mudra segment evidence while still incorporating the expression confidence where available. This is a transparent numeric score, not a claim of semantic equivalence.

Uncertainty states are assigned explicitly:

- `normal`
- `low_confidence`
- `missing_modality`
- `insufficient_evidence`

The service does not convert missing predictions into valid detections.

## Alignment output structure

The output is attached to the existing fusion result as `mudra_bhava_alignment`.

Example structure:

```python
{
  "video_id": "...",
  "analysis_id": "...",
  "alignment_id": "...",
  "alignments": [
    {
      "mudra_segment_id": "...",
      "mudra_label": "Pataka",
      "mudra_start_timestamp": 0.0,
      "mudra_end_timestamp": 2.0,
      "mudra_confidence": 0.92,
      "expression_observations": [
        {
          "label": "Happy",
          "start_timestamp": 0.5,
          "end_timestamp": 1.5,
          "confidence": 0.81,
          "frame_number": 12,
          "filename": "frame_000012.jpg",
        }
      ],
      "expression_labels": ["Happy"],
      "expression_confidences": [0.81],
      "overlap_duration": 1.0,
      "mudra_coverage_ratio": 0.5,
      "alignment_status": "aligned",
      "uncertainty_status": "normal",
      "alignment_method": "interval_overlap",
      "alignment_confidence": 0.76,
    }
  ],
  "summary": {
    "total_mudra_segments": 1,
    "total_expression_observations": 1,
    "aligned_segments": 1,
    "partial_overlap_segments": 0,
    "no_expression_observation_segments": 0,
    "insufficient_evidence_segments": 0,
  },
  "status": "completed",
}
```

## API integration

This phase intentionally keeps the existing Mudra and Bhava APIs intact and integrates the new structure into the existing fusion result path.

The added field is optional and does not replace any legacy contract:

- `mudra_bhava_alignment` in the `FusionResponse` schema
- attached inside the result returned by `fuse_video()`

No frontend work was introduced, and no new story-generation behavior was added.

## Test coverage added

The Phase 2 test file is:

- `backend/tests/test_mudra_bhava_alignment_service.py`

It covers:

- single overlapping Mudra and Bhava interval
- multiple expression observations
- partial temporal overlap
- no temporal overlap
- missing expression observations
- low-confidence observations
- invalid timestamps
- duplicate timestamps
- out-of-order timestamps
- empty inputs
- overlap duration and coverage ratio
- video_id and analysis_id isolation
- preservation of original model labels and confidence values
- fusion result payload integration

## Actual validation results

Command executed:

```bash
cd C:\Users\selva\HI_NatyaVerse\backend
pytest tests/test_mudra_bhava_alignment_service.py tests/test_mudra_service.py tests/test_fusion_service.py tests/test_story_service.py tests/test_bhava_service.py -q
```

Actual output:

```text
........................................................................ [ 93%]
.............                                                             [100%]
85 passed in 1.62s
```

## Current limitations

This implementation is intentionally conservative. It does not:

- infer cultural meaning from temporal overlap
- convert FER labels into Bhava labels
- invent missing timestamps or durations
- treat generic emotion predictions as classical Bharatanatyam semantics
- cross-check body pose or narrative interpretation beyond the existing architecture

This remains a temporal evidence layer, not a cultural or expressive interpretation layer.
