import json
from types import SimpleNamespace

import pytest

from app.services.knowledge_service import (
    KnowledgeService,
    _validate_structured_document,
    normalize_label,
)


def _claim(
    claim_id="claim-pataka",
    *,
    status="verified",
    sources=None,
    conditions=None,
    description="Flag / banner",
):
    return {
        "claim_id": claim_id,
        "concept_id": None,
        "descriptions": {"en": description},
        "context_conditions": conditions or [],
        "usage_conditions": [],
        "verification_status": status,
        "sources": sources if sources is not None else [{
            "reference": "Example source reference",
            "bibliographic_details": None,
        }],
        "uncertainty_notes": [],
    }


def _entry(
    name="Pataka",
    *,
    aliases=None,
    status="verified",
    claims=None,
):
    return {
        "mudra_id": f"mudra-{normalize_label(name)}",
        "canonical_name": name,
        "normalized_label": normalize_label(name),
        "approved_aliases": aliases or [],
        "knowledge_status": status,
        "meaning_claims": claims if claims is not None else [
            _claim(f"claim-{normalize_label(name)}")
        ],
        "uncertainty_notes": [],
    }


def _document(*entries):
    return {
        "schema_version": "2.0",
        "metadata": {
            "description": "Test knowledge fixture",
            "curation_status": "test",
            "curation_note": "Fixture only.",
        },
        "entries": list(entries),
    }


def _service(monkeypatch, tmp_path, payload):
    path = tmp_path / "mudra_knowledge.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "app.services.knowledge_service.settings",
        SimpleNamespace(mudra_knowledge_path=path),
    )
    return KnowledgeService(), path


def test_actual_versioned_knowledge_schema_and_legacy_entries_are_preserved():
    from app.config import settings
    from app.utils.json_utils import load_json

    document = load_json(settings.mudra_knowledge_path)
    entries = _validate_structured_document(document)

    assert len(entries) == 48
    assert sum(bool(entry["meaning_claims"]) for entry in entries.values()) == 11
    assert sum(entry["knowledge_status"] == "pending_research" for entry in entries.values()) == 37
    pataka = next(entry for entry in entries.values() if entry["canonical_name"] == "Pataka")
    assert pataka["meaning_claims"][0]["descriptions"]["en"] == "Flag / banner"
    assert pataka["meaning_claims"][0]["sources"][0]["reference"] == (
        "Abhinaya Darpanam (canonical namesake)"
    )
    assert pataka["meaning_claims"][0]["sources"][0]["bibliographic_details"] is None


def test_structured_schema_rejects_invalid_normalization_and_missing_source_shape():
    invalid = _document(_entry())
    invalid["entries"][0]["normalized_label"] = "not-pataka"

    with pytest.raises(ValueError, match="normalized_label"):
        _validate_structured_document(invalid)

    invalid = _document(_entry(claims=[_claim(sources=[{"reference": "", "bibliographic_details": None}])]))
    with pytest.raises(ValueError, match="sources"):
        _validate_structured_document(invalid)


def test_legacy_json_is_loaded_without_inventing_aliases_or_claims(monkeypatch, tmp_path):
    service, _ = _service(
        monkeypatch,
        tmp_path,
        {
            "_metadata": {"schema_version": "1.0"},
            "Pataka": {
                "meaning": "Flag / banner",
                "usage": [],
                "associated_bhava": [],
                "source": "Abhinaya Darpanam",
                "status": "curated",
            },
            "Aralam": {
                "meaning": None,
                "usage": [],
                "associated_bhava": [],
                "source": None,
                "status": "pending_research",
            },
        },
    )

    result = service.retrieve_mudra("pAtAkA")
    assert result["status"] == "partially_verified"
    assert result["claim"]["descriptions"]["en"] == "Flag / banner"
    assert result["claim"]["sources"][0]["reference"] == "Abhinaya Darpanam"
    assert service.retrieve_mudra("Aralam")["status"] == "pending_research"
    assert service.retrieve_mudra("Pataka Alias")["status"] == "unknown_label"


def test_normalized_canonical_and_explicit_alias_resolution(monkeypatch, tmp_path):
    service, _ = _service(
        monkeypatch,
        tmp_path,
        _document(_entry(aliases=["Approved Form"])),
    )

    assert service.retrieve_mudra("  PATAKA ")["status"] == "verified"
    assert service.retrieve_mudra("approved-form")["canonical_name"] == "Pataka"


def test_ambiguous_alias_is_not_arbitrarily_resolved(monkeypatch, tmp_path):
    service, _ = _service(
        monkeypatch,
        tmp_path,
        _document(_entry("Pataka", aliases=["Shared"]), _entry("Tripathaka", aliases=["Shared"])),
    )

    assert service.retrieve_mudra("shared")["status"] == "ambiguous_label"


def test_missing_unknown_malformed_and_invalid_knowledge_are_distinguished(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    assert service.retrieve_mudra("unknown")["status"] == "unknown_label"

    missing = tmp_path / "missing.json"
    monkeypatch.setattr(
        "app.services.knowledge_service.settings",
        SimpleNamespace(mudra_knowledge_path=missing),
    )
    assert KnowledgeService().retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"

    malformed, _ = _service(monkeypatch, tmp_path, "{invalid")
    assert malformed.retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"

    invalid, _ = _service(monkeypatch, tmp_path, {"schema_version": "2.0", "entries": []})
    assert invalid.retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"


def test_verified_partial_pending_context_and_sources_are_explicit(monkeypatch, tmp_path):
    partial = _entry(
        "Tripathaka",
        status="partially_verified",
        claims=[_claim("claim-tripathaka", status="partially_verified")],
    )
    contextual = _entry(
        "Mayura",
        status="verified",
        claims=[_claim("claim-mayura", conditions=[{"key": "performance", "value": "test"}])],
    )
    pending = _entry(
        "Aralam",
        status="pending_research",
        claims=[_claim("claim-aralam", status="pending_research")],
    )
    missing_source = _entry(
        "Anjali",
        status="verified",
        claims=[_claim("claim-anjali", sources=[])],
    )
    unverified = _entry(
        "Mushti",
        status="unverified",
        claims=[_claim("claim-mushti", status="unverified")],
    )
    service, _ = _service(
        monkeypatch,
        tmp_path,
        _document(_entry(), partial, contextual, pending, missing_source, unverified),
    )

    assert service.retrieve_mudra("Pataka")["claim"]["sources"][0]["reference"] == "Example source reference"
    assert service.retrieve_mudra("Pataka")["status"] == "verified"
    assert service.retrieve_mudra("Pataka")["claim"]["verification_status"] == "verified"
    assert service.retrieve_mudra("Tripathaka")["status"] == "partially_verified"
    assert service.retrieve_mudra("Tripathaka")["claim"]["claim_id"] == "claim-tripathaka"
    assert service.retrieve_mudra("Pataka")["claim"]["descriptions"]["en"] == "Flag / banner"
    assert service.retrieve_mudra("Pataka")["claim"]["context_conditions"] == []
    assert service.retrieve_mudra("Pataka")["claim"]["usage_conditions"] == []
    assert service.retrieve_mudra("Pataka")["claim"]["concept_id"] is None
    assert service.retrieve_mudra("Pataka")["claim"]["uncertainty_notes"] == []
    assert service.retrieve_mudra("Pataka")["canonical_name"] == "Pataka"
    assert service.retrieve_mudra("Pataka")["mudra_id"] == "mudra-pataka"
    assert service.retrieve_mudra("Pataka")["normalized_label"] == "pataka"
    assert service.retrieve_mudra("Pataka")["matched_label"] == "Pataka"
    assert service.retrieve_mudra("Mayura")["status"] == "context_required"
    assert service.retrieve_mudra("Mayura", context={"performance": "test"})["status"] == "verified"
    assert service.retrieve_mudra("Aralam")["status"] == "pending_research"
    assert service.retrieve_mudra("Anjali")["status"] == "missing_source_reference"
    assert service.retrieve_mudra("Mushti")["status"] == "unverified"


def test_legacy_evidence_exposes_verified_and_partial_status_separately(monkeypatch, tmp_path):
    verified = _entry("Pataka", status="verified")
    partial = _entry(
        "Tripathaka",
        status="partially_verified",
        claims=[_claim("claim-tripathaka", status="partially_verified")],
    )
    service, _ = _service(monkeypatch, tmp_path, _document(verified, partial))

    evidence = service.build_evidence({
        "mudra": {
            "detections": [
                {"name": "Pataka", "confidence": 0.9},
                {"name": "Tripathaka", "confidence": 0.9},
            ]
        }
    })

    assert [item["verification_status"] for item in evidence["grounded"]] == [
        "verified",
        "partially_verified",
    ]
    assert all(item["source_references"] for item in evidence["grounded"])


def test_equally_applicable_meanings_are_reported_ambiguous(monkeypatch, tmp_path):
    claims = [
        _claim("claim-one", description="Meaning one"),
        _claim("claim-two", description="Meaning two"),
    ]
    service, _ = _service(monkeypatch, tmp_path, _document(_entry(claims=claims)))

    assert service.retrieve_mudra("Pataka")["status"] == "ambiguous_meaning"


def test_context_selects_only_applicable_claim(monkeypatch, tmp_path):
    claims = [
        _claim(
            "claim-temple",
            status="partially_verified",
            conditions=[{"key": "setting", "value": "temple"}],
            description="Temple-context claim",
        ),
        _claim(
            "claim-stage",
            status="partially_verified",
            conditions=[{"key": "setting", "value": "stage"}],
            description="Stage-context claim",
        ),
    ]
    service, _ = _service(
        monkeypatch,
        tmp_path,
        _document(_entry(status="partially_verified", claims=claims)),
    )

    assert service.retrieve_mudra("Pataka")["status"] == "context_required"
    assert service.retrieve_mudra("Pataka", context={"setting": "temple"})["claim"]["claim_id"] == "claim-temple"
    assert service.retrieve_mudra("Pataka", context={"setting": "stage"})["claim"]["claim_id"] == "claim-stage"
    assert service.retrieve_mudra(
        "Pataka", context={"setting": "temple", "other": "stage"}
    )["status"] == "partially_verified"


def test_segment_evidence_withholds_low_confidence_and_preserves_phase1_fields(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    result = {
        "video_id": "video-a",
        "analysis_id": "analysis-a",
        "temporal_sequence": {
            "video_id": "video-a",
            "analysis_id": "analysis-a",
            "segments": [
                {
                    "video_id": "video-a",
                    "analysis_id": "analysis-a",
                    "segment_id": "segment-1",
                    "mudra_label": "Pataka",
                    "start_timestamp": 1.0,
                    "end_timestamp": 2.0,
                    "frame_indices": [10, 11],
                    "supporting_evidence_ids": ["analysis-a-frame-10"],
                    "confidence": {"mean": 0.9},
                    "uncertainty_status": "normal",
                },
                {
                    "video_id": "video-a",
                    "analysis_id": "analysis-a",
                    "segment_id": "segment-2",
                    "mudra_label": "Pataka",
                    "start_timestamp": 3.0,
                    "end_timestamp": 4.0,
                    "frame_indices": [12],
                    "supporting_evidence_ids": ["analysis-a-frame-12"],
                    "confidence": {"mean": 0.4},
                    "uncertainty_status": "low_confidence",
                },
            ],
        },
    }

    evidence = service.build_cultural_evidence(
        result,
        video_id="video-a",
        analysis_id="analysis-a",
    )

    assert evidence[0]["claim_id"] == "claim-pataka"
    assert evidence[0]["source_references"] == ["Example source reference"]
    assert evidence[0]["frame_indices"] == [10, 11]
    assert evidence[0]["evidence_ids"] == ["analysis-a-frame-10"]
    assert evidence[1]["knowledge_status"] == "withheld_low_confidence"
    assert evidence[1]["claim"] is None
    assert evidence[1]["reason"]


def test_alignment_is_observation_only_and_identifiers_are_enforced(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    result = {
        "temporal_sequence": {
            "video_id": "video-a",
            "analysis_id": "analysis-a",
            "segments": [{
                "video_id": "video-a",
                "analysis_id": "analysis-a",
                "segment_id": "segment-1",
                "mudra_label": "Pataka",
                "start_timestamp": 1.0,
                "end_timestamp": 2.0,
                "frame_indices": [10],
                "supporting_evidence_ids": ["analysis-a-frame-10"],
                "confidence": {"mean": 0.9},
                "uncertainty_status": "normal",
            }],
        },
    }
    alignment = {
        "alignments": [{
            "mudra_segment_id": "segment-1",
            "alignment_status": "aligned",
            "uncertainty_status": "normal",
            "expression_observations": [{"label": "Happy"}],
            "overlap_duration": 1.0,
            "mudra_coverage_ratio": 1.0,
        }]
    }
    evidence = service.build_cultural_evidence(
        result,
        video_id="video-a",
        analysis_id="analysis-a",
        alignment=alignment,
    )[0]
    assert evidence["alignment_observation"]["expression_observations"] == [{"label": "Happy"}]
    assert evidence["claim"]["descriptions"]["en"] == "Flag / banner"
    assert "bhava" not in evidence["claim"]
    assert "rasa" not in evidence["claim"]

    with pytest.raises(ValueError, match="different video"):
        service.build_cultural_evidence(result, video_id="video-b", analysis_id="analysis-a")
    with pytest.raises(ValueError, match="different analysis"):
        service.build_cultural_evidence(result, video_id="video-a", analysis_id="analysis-b")


@pytest.mark.parametrize(
    "confidence",
    [None, float("nan"), 1.1],
)
def test_missing_or_invalid_recognition_confidence_withholds_claim(
    monkeypatch, tmp_path, confidence
):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    segment = {
        "video_id": "video-a",
        "analysis_id": "analysis-a",
        "segment_id": "segment-invalid",
        "mudra_label": "Pataka",
        "start_timestamp": 1.0,
        "end_timestamp": 2.0,
        "frame_indices": [1],
        "supporting_evidence_ids": [],
        "confidence": {"mean": confidence},
        "uncertainty_status": "normal",
    }
    evidence = service.build_cultural_evidence(
        {
            "temporal_sequence": {
                "video_id": "video-a",
                "analysis_id": "analysis-a",
                "segments": [segment],
            }
        },
        video_id="video-a",
        analysis_id="analysis-a",
    )[0]

    assert evidence["knowledge_status"] == "withheld_low_confidence"
    assert evidence["claim"] is None


def test_legacy_evidence_does_not_ground_low_confidence_recognition(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    evidence = service.build_evidence({
        "mudra": {
            "detections": [
                {"name": "Pataka", "confidence": 0.4},
                {"name": "Tripathaka", "confidence": float("nan")},
            ]
        }
    })

    assert evidence["grounded"] == []
    assert len(evidence["unresolved"]) == 2
    assert all("confidence" in item["detail"] for item in evidence["unresolved"])


def test_invalid_temporal_segment_does_not_receive_a_cultural_claim(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    evidence = service.build_cultural_evidence(
        {
            "temporal_sequence": {
                "video_id": "video-a",
                "analysis_id": "analysis-a",
                "segments": [{
                    "video_id": "video-a",
                    "analysis_id": "analysis-a",
                    "segment_id": "segment-invalid",
                    "mudra_label": "Pataka",
                    "start_timestamp": 3.0,
                    "end_timestamp": 2.0,
                    "confidence": {"mean": 0.9},
                }],
            }
        },
        video_id="video-a",
        analysis_id="analysis-a",
    )[0]

    assert evidence["knowledge_status"] == "invalid_temporal_evidence"
    assert evidence["claim"] is None


@pytest.mark.parametrize(
    "invalid_field",
    ["entry_extra", "claim_extra", "context_extra", "source_extra", "invalid_status", "invalid_source"],
)
def test_runtime_json_schema_rejects_invalid_nested_knowledge(
    monkeypatch, tmp_path, invalid_field
):
    claim = _claim(conditions=[{"key": "setting", "value": "stage"}])
    entry = _entry(claims=[claim])
    if invalid_field == "entry_extra":
        entry["unexpected"] = True
    elif invalid_field == "claim_extra":
        claim["unexpected"] = True
    elif invalid_field == "context_extra":
        claim["context_conditions"][0]["unexpected"] = True
    elif invalid_field == "source_extra":
        claim["sources"][0]["unexpected"] = True
    elif invalid_field == "invalid_status":
        claim["verification_status"] = "curated"
    else:
        claim["sources"][0]["reference"] = ""

    service, _ = _service(monkeypatch, tmp_path, _document(entry))

    assert service.retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"
    assert service.load_error()


def test_runtime_json_schema_file_is_required(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    missing_schema = tmp_path / "missing.schema.json"
    monkeypatch.setattr(
        "app.services.knowledge_service.KNOWLEDGE_SCHEMA_PATH",
        missing_schema,
    )

    assert service.retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"


def test_runtime_json_schema_itself_must_be_valid(monkeypatch, tmp_path):
    service, _ = _service(monkeypatch, tmp_path, _document(_entry()))
    invalid_schema = tmp_path / "invalid.schema.json"
    invalid_schema.write_text('{"type": "not-a-json-schema-type"}', encoding="utf-8")
    monkeypatch.setattr(
        "app.services.knowledge_service.KNOWLEDGE_SCHEMA_PATH",
        invalid_schema,
    )

    assert service.retrieve_mudra("Pataka")["status"] == "knowledge_unavailable"
