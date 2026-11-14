from app.services import fusion_service
from app.services.mudra_bhava_alignment_service import (
    align_mudra_bhava_sequences,
    calculate_temporal_overlap,
)


def test_alignment_overlaps_single_expression_observation():
    mudra_result = {
        "video_id": "11111111-1111-4111-8111-111111111111",
        "analysis_id": "11111111-1111-4111-8111-111111111111",
        "temporal_sequence": {
            "segments": [
                {
                    "segment_id": "seg-1",
                    "mudra_label": "Pataka",
                    "start_timestamp": 0.0,
                    "end_timestamp": 2.0,
                    "confidence": 0.92,
                }
            ]
        },
    }
    bhava_result = {
        "video_id": "11111111-1111-4111-8111-111111111111",
        "analysis_id": "11111111-1111-4111-8111-111111111111",
        "bhava_events": [
            {"bhava": "Happy", "start_time": 0.5, "end_time": 1.5, "confidence": 0.81}
        ],
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="11111111-1111-4111-8111-111111111111", analysis_id="11111111-1111-4111-8111-111111111111")

    assert result["alignments"][0]["alignment_status"] == "aligned"
    assert result["alignments"][0]["expression_labels"] == ["Happy"]
    assert result["alignments"][0]["overlap_duration"] == 1.0
    assert result["alignments"][0]["mudra_coverage_ratio"] == 0.5


def test_alignment_handles_multiple_expression_observations_and_partial_overlap():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Mayura", "start_timestamp": 0.0, "end_timestamp": 4.0, "confidence": 0.7}]
        }
    }
    bhava_result = {
        "bhava_events": [
            {"bhava": "Happy", "start_time": 0.1, "end_time": 0.2, "confidence": 0.86},
            {"bhava": "Neutral", "start_time": 3.8, "end_time": 3.9, "confidence": 0.72},
        ]
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="22222222-2222-4222-8222-222222222222", analysis_id="22222222-2222-4222-8222-222222222222")

    assert result["alignments"][0]["alignment_status"] == "partial_overlap"
    assert result["alignments"][0]["expression_labels"] == ["Happy", "Neutral"]
    assert result["alignments"][0]["overlap_duration"] == 0.2
    assert result["alignments"][0]["mudra_coverage_ratio"] == 0.05


def test_alignment_detects_no_overlap_and_missing_observations():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 2.0, "confidence": 0.9}]
        }
    }
    bhava_result = {
        "bhava_events": [{"bhava": "Angry", "start_time": 3.0, "end_time": 5.0, "confidence": 0.88}]
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="33333333-3333-4333-8333-333333333333", analysis_id="33333333-3333-4333-8333-333333333333")

    assert result["alignments"][0]["alignment_status"] == "no_expression_observation"
    assert result["alignments"][0]["uncertainty_status"] == "missing_modality"


def test_alignment_handles_low_confidence_and_invalid_input():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Aralam", "start_timestamp": 0.0, "end_timestamp": 2.0, "confidence": 0.2}]
        }
    }
    bhava_result = {
        "frames": [{"bhava": "Sad", "timestamp": 1.0, "confidence": 0.3}]
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="44444444-4444-4444-8444-444444444444", analysis_id="44444444-4444-4444-8444-444444444444")
    aligned = result["alignments"][0]

    assert aligned["uncertainty_status"] == "low_confidence"
    assert aligned["alignment_confidence"] <= 1.0

    empty = align_mudra_bhava_sequences([], {}, video_id="55555555-5555-4555-8555-555555555555", analysis_id="55555555-5555-4555-8555-555555555555")
    assert empty["alignments"] == []

    invalid = align_mudra_bhava_sequences(
        {"temporal_sequence": {"segments": [{"mudra_label": "Pataka", "start_timestamp": "bad", "end_timestamp": 2.0, "confidence": 0.7}]}},
        {"frames": [{"bhava": "Happy", "timestamp": "bad", "confidence": 0.9}]},
        video_id="66666666-6666-4666-8666-666666666666",
        analysis_id="66666666-6666-4666-8666-666666666666",
    )
    assert invalid["alignments"] == []


def test_alignment_supports_duplicate_and_out_of_order_timestamps():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 2.0, "confidence": 0.9}]
        }
    }
    bhava_result = {
        "frames": [
            {"bhava": "Happy", "timestamp": 2.0, "confidence": 0.7},
            {"bhava": "Neutral", "timestamp": 1.5, "confidence": 0.6},
            {"bhava": "Neutral", "timestamp": 1.5, "confidence": 0.6},
        ]
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="77777777-7777-4777-8777-777777777777", analysis_id="77777777-7777-4777-8777-777777777777")
    alignment = result["alignments"][0]

    assert alignment["alignment_method"] in {"point_timestamp_match", "interval_overlap"}
    assert alignment["expression_labels"]
    assert alignment["overlap_duration"] >= 0.0


def test_alignment_distinguishes_point_matches_from_interval_coverage():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 2.0, "confidence": 0.9}]
        }
    }

    point_inside = align_mudra_bhava_sequences(
        mudra_result,
        {"frames": [{"bhava": "Happy", "timestamp": 1.0, "confidence": 0.8}]},
        video_id="aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        analysis_id="aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )["alignments"][0]
    assert point_inside["point_match_count"] == 1
    assert point_inside["overlap_duration"] == 0.0
    assert point_inside["mudra_coverage_ratio"] == 0.0
    assert point_inside["alignment_status"] == "partial_overlap"

    point_outside = align_mudra_bhava_sequences(
        mudra_result,
        {"frames": [{"bhava": "Neutral", "timestamp": 5.0, "confidence": 0.7}]},
        video_id="bbbbbbb2-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        analysis_id="bbbbbbb2-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )["alignments"][0]
    assert point_outside["point_match_count"] == 0
    assert point_outside["alignment_status"] == "no_expression_observation"

    interval_full = align_mudra_bhava_sequences(
        mudra_result,
        {"bhava_events": [{"bhava": "Happy", "start_time": 0.0, "end_time": 2.0, "confidence": 0.82}]},
        video_id="ccccccc3-cccc-4ccc-8ccc-cccccccccccc",
        analysis_id="ccccccc3-cccc-4ccc-8ccc-cccccccccccc",
    )["alignments"][0]
    assert interval_full["overlap_duration"] == 2.0
    assert interval_full["mudra_coverage_ratio"] == 1.0

    interval_partial = align_mudra_bhava_sequences(
        mudra_result,
        {"bhava_events": [{"bhava": "Angry", "start_time": 0.5, "end_time": 1.5, "confidence": 0.8}]},
        video_id="ddddddd4-dddd-4ddd-8ddd-dddddddddddd",
        analysis_id="ddddddd4-dddd-4ddd-8ddd-dddddddddddd",
    )["alignments"][0]
    assert interval_partial["overlap_duration"] == 1.0
    assert interval_partial["mudra_coverage_ratio"] == 0.5

    multiple_intervals = align_mudra_bhava_sequences(
        {"temporal_sequence": {"segments": [{"segment_id": "seg-1", "mudra_label": "Mayura", "start_timestamp": 0.0, "end_timestamp": 4.0, "confidence": 0.8}]}},
        {"bhava_events": [
            {"bhava": "Happy", "start_time": 0.5, "end_time": 2.5, "confidence": 0.8},
            {"bhava": "Neutral", "start_time": 1.5, "end_time": 3.5, "confidence": 0.7},
        ]},
        video_id="eeeeeee5-eeee-4eee-8eee-eeeeeeeeeeee",
        analysis_id="eeeeeee5-eeee-4eee-8eee-eeeeeeeeeeee",
    )["alignments"][0]
    assert multiple_intervals["overlap_duration"] == 3.0
    assert multiple_intervals["mudra_coverage_ratio"] == 0.75


def test_alignment_handles_out_of_order_and_empty_interval_observations():
    mudra_result = {
        "temporal_sequence": {
            "segments": [{"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 2.0, "confidence": 0.9}]
        }
    }
    bhava_result = {
        "frames": [
            {"bhava": "Neutral", "timestamp": 2.0, "confidence": 0.7},
            {"bhava": "Happy", "timestamp": 1.0, "confidence": 0.8},
            {"bhava": "Happy", "timestamp": 1.0, "confidence": 0.8},
        ]
    }
    result = align_mudra_bhava_sequences(mudra_result, bhava_result, video_id="ffffffff-ffff-4fff-8fff-ffffffffffff", analysis_id="ffffffff-ffff-4fff-8fff-ffffffffffff")
    alignment = result["alignments"][0]
    assert alignment["alignment_status"] in {"aligned", "partial_overlap"}
    assert alignment["point_match_count"] >= 1
    assert alignment["expression_labels"]

    empty_point_result = align_mudra_bhava_sequences(
        mudra_result,
        {"frames": [{"bhava": "Happy", "timestamp": 10.0, "confidence": 0.8}]},
        video_id="11111111-1111-4111-8111-111111111111",
        analysis_id="11111111-1111-4111-8111-111111111111",
    )["alignments"][0]
    assert empty_point_result["alignment_status"] == "no_expression_observation"


def test_alignment_isolates_video_and_analysis_data():
    mudra_result_one = {"temporal_sequence": {"segments": [{"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 1.0, "confidence": 0.8}]}}
    bhava_result_one = {"frames": [{"bhava": "Happy", "timestamp": 0.5, "confidence": 0.9}]}
    mudra_result_two = {"temporal_sequence": {"segments": [{"segment_id": "seg-1", "mudra_label": "Mayura", "start_timestamp": 0.0, "end_timestamp": 1.0, "confidence": 0.7}]}}
    bhava_result_two = {"frames": [{"bhava": "Sad", "timestamp": 0.5, "confidence": 0.8}]}

    first = align_mudra_bhava_sequences(mudra_result_one, bhava_result_one, video_id="88888888-8888-4888-8888-888888888888", analysis_id="88888888-8888-4888-8888-888888888888")
    second = align_mudra_bhava_sequences(mudra_result_two, bhava_result_two, video_id="99999999-9999-4999-8999-999999999999", analysis_id="99999999-9999-4999-8999-999999999999")

    assert first["video_id"] != second["video_id"]
    assert first["analysis_id"] != second["analysis_id"]
    assert first["alignments"][0]["mudra_label"] == "Pataka"
    assert second["alignments"][0]["mudra_label"] == "Mayura"


def test_expression_observations_are_ordered_chronologically():
    mudra_result = {
        "temporal_sequence": {
            "segments": [
                {"segment_id": "seg-1", "mudra_label": "Pataka", "start_timestamp": 0.0, "end_timestamp": 3.0, "confidence": 0.9}
            ]
        }
    }
    bhava_result = {
        "frames": [
            {"bhava": "Surprise", "timestamp": 2.5, "confidence": 0.7},
            {"bhava": "Happy", "start_timestamp": 0.5, "end_timestamp": 1.0, "confidence": 0.8},
            {"bhava": "Neutral", "timestamp": 1.5, "confidence": 0.9},
        ]
    }

    result = align_mudra_bhava_sequences(mudra_result, bhava_result)
    alignment = result["alignments"][0]

    assert alignment["expression_labels"] == ["Happy", "Neutral", "Surprise"]
    assert [
        observation["start_timestamp"]
        for observation in alignment["expression_observations"]
    ] == [0.5, 1.5, 2.5]


def test_fusion_result_contains_alignment_payload(monkeypatch):
    def fake_get(analysis_id, modality):
        if modality == "mudra":
            return {
                "video_id": analysis_id,
                "analysis_id": analysis_id,
                "frame_count": 2,
                "mudra_events": [{"mudra": "Pataka", "start_time": 0.0, "end_time": 1.0, "confidence": 0.9, "frame_count": 2}],
                "summary": {"dominant_mudra": "Pataka", "average_confidence": 0.9},
                "mudra": {"detections": [{"name": "Pataka", "confidence": 0.9, "grounded": True, "status": "grounded", "timestamps": [0.0, 1.0]}]},
                "evidence": {"grounded": [{"id": "mudra-Pataka", "label": "Pataka"}], "detected": [], "unresolved": [], "interpreted": []},
            }
        if modality == "bhava":
            return {
                "video_id": analysis_id,
                "analysis_id": analysis_id,
                "frame_count": 2,
                "bhava_events": [{"bhava": "Happy", "start_time": 0.5, "end_time": 1.5, "confidence": 0.8, "frame_count": 2}],
                "summary": {"dominant_bhava": "Happy", "average_confidence": 0.8},
                "bhava": {"dominant_emotion": "Happy", "confidence": 0.8, "detections": [{"name": "Happy", "confidence": 0.8, "timestamps": [0.5, 1.5]}], "segments": [{"label": "Happy", "start": 0.5, "end": 1.5, "confidence": 0.8}]},
                "evidence": {"grounded": [], "detected": [{"id": "bhava-Happy", "label": "Happy"}], "unresolved": [], "interpreted": []},
            }
        raise KeyError(modality)

    monkeypatch.setattr(fusion_service, "get_modality_result", fake_get)
    monkeypatch.setattr(fusion_service, "save_result", lambda _: None)
    monkeypatch.setattr(fusion_service, "save_modality_result", lambda *_: None)

    result = fusion_service.fuse_video("10101010-1010-4010-8010-101010101010")

    assert "mudra_bhava_alignment" in result
    assert result["mudra_bhava_alignment"]["alignments"][0]["mudra_label"] == "Pataka"
    assert result["mudra_bhava_alignment"]["alignments"][0]["expression_labels"] == ["Happy"]


def test_overlap_helper_handles_interval_overlap():
    assert calculate_temporal_overlap(0.0, 2.0, 1.5, 3.5) == 0.5
    assert calculate_temporal_overlap(0.0, 1.0, 2.0, 3.0) == 0.0
