from app.api.routes import frame_analysis


def test_frame_analysis_preserves_mudra_verification_and_provenance(monkeypatch):
    video_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(
        frame_analysis,
        "get_manifest_for_video",
        lambda _: {"frames": [{"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"}]},
    )
    results = {
        "mudra": {
            "frames": [{
                "frame_number": 0,
                "mudra": "Pataka",
                "confidence": 0.9,
                "meaning": "Flag / banner",
                "status": "grounded",
                "knowledge_status": "partially_verified",
                "verification_status": "partially_verified",
                "claim_id": "claim-pataka",
                "source_references": ["project namesake gloss"],
                "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                "uncertainty_reason": None,
            }],
        },
        "bhava": {"frames": [{"frame_number": 0, "bhava": "Happy", "confidence": 0.8}]},
        "pose": {"frames": []},
    }
    monkeypatch.setattr(
        frame_analysis,
        "get_modality_result",
        lambda _, modality: results[modality],
    )

    frame = frame_analysis.build_frame_level_analysis(video_id)["frames"][0]

    assert frame["mudra"]["meaning"] == "Flag / banner"
    assert frame["mudra"]["knowledge_status"] == "partially_verified"
    assert frame["mudra"]["verification_status"] == "partially_verified"
    assert frame["mudra"]["claim_id"] == "claim-pataka"
    assert frame["mudra"]["source_references"] == ["project namesake gloss"]
    assert frame["mudra"]["uncertainty_notes"] == ["Bibliographic provenance is incomplete."]
    assert "partially verified" in frame["mudra"]["explanation"]
