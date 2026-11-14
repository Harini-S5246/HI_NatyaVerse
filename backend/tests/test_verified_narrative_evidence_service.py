"""Focused tests for explicit, production-eligible narrative evidence."""
from copy import deepcopy

import pytest

from app.services import verified_narrative_evidence_service as service
from app.services.performance_interpretation_service import build_from_verified_narrative_evidence


ANALYSIS_ID = "11111111-1111-1111-1111-111111111111"


def _payload(analysis_id=ANALYSIS_ID):
    provenance = {"source_reference": "annotated performance log, event 1", "annotator_or_verifier": "Named expert", "method": "direct performance review", "verification_confidence": 1.0}
    return {
        "analysis_id": analysis_id, "video_id": analysis_id,
        "performance_mode": {"label": "narrative_dance", "verification_status": "verified", "source": {"type": "expert_verification", "reference": "expert-review-2026-01"}, "provenance": deepcopy(provenance)},
        "records": [{
            "evidence_id": "verified-event-001", "analysis_id": analysis_id, "video_id": analysis_id,
            "statement": "Verified narrative event: Performer A greets Performer B.", "statement_type": "verified_narrative_event",
            "source": {"type": "expert_verification", "reference": "expert-review-2026-01"}, "provenance": provenance,
            "span": {"start_time": 0.0, "end_time": 2.0}, "verification_status": "verified",
            "verification_method": "human_or_curated_source", "production_eligibility": {"status": "eligible"},
        }],
    }


def test_valid_evidence_is_persisted_with_provenance(monkeypatch):
    saved = []
    monkeypatch.setattr(service, "save_modality_result", lambda *args: saved.append(args))
    artifact = service.create_verified_narrative_evidence(ANALYSIS_ID, _payload())
    assert artifact["records"][0]["provenance"]["annotator_or_verifier"] == "Named expert"
    assert artifact["records"][0]["production_eligibility"] == {"status": "eligible"}
    assert saved[0][0:2] == (ANALYSIS_ID, "narrative_evidence")


def test_missing_provenance_is_rejected():
    payload = _payload()
    del payload["records"][0]["provenance"]
    with pytest.raises(service.VerifiedNarrativeEvidenceValidationError, match="unsupported fields"):
        service.create_verified_narrative_evidence(ANALYSIS_ID, payload)


def test_unverified_evidence_cannot_become_production_eligible():
    payload = _payload()
    payload["records"][0]["verification_status"] = "unverified"
    with pytest.raises(service.VerifiedNarrativeEvidenceValidationError, match="production-eligible"):
        service.create_verified_narrative_evidence(ANALYSIS_ID, payload)


@pytest.mark.parametrize("forbidden_key", ["mudra", "bhava", "fusion"])
def test_model_or_fusion_payload_fields_are_rejected(forbidden_key):
    payload = _payload()
    payload["records"][0][forbidden_key] = {"label": "not a verified narrative statement"}
    with pytest.raises(service.VerifiedNarrativeEvidenceValidationError, match="unsupported fields"):
        service.create_verified_narrative_evidence(ANALYSIS_ID, payload)


def test_analysis_id_mismatch_is_rejected():
    with pytest.raises(service.VerifiedNarrativeEvidenceValidationError, match="different analysis"):
        service.create_verified_narrative_evidence(ANALYSIS_ID, _payload("22222222-2222-2222-2222-222222222222"))


def test_package_contains_only_explicitly_verified_events():
    artifact = _payload()
    artifact["schema_version"] = service.SCHEMA_VERSION
    artifact["created_at"] = "2026-01-01T00:00:00+00:00"
    package = build_from_verified_narrative_evidence(ANALYSIS_ID, artifact)
    assert package["production_eligible"] is True
    assert package["evidence_coverage"]["eligible_verified_records"] == 1
    assert [event["event_id"] for event in package["events"]] == ["verified-event-001"]
    assert package["events"][0]["statement"] == artifact["records"][0]["statement"]


def test_cross_analysis_artifact_cannot_create_package():
    artifact = _payload("22222222-2222-2222-2222-222222222222")
    artifact["schema_version"] = service.SCHEMA_VERSION
    artifact["created_at"] = "2026-01-01T00:00:00+00:00"
    with pytest.raises(service.VerifiedNarrativeEvidenceValidationError, match="different analysis"):
        build_from_verified_narrative_evidence(ANALYSIS_ID, artifact)
