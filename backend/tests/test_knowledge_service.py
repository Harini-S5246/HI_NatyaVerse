"""Tests for the curated knowledge grounding and evidence assembly module."""
from types import SimpleNamespace

from app.services.knowledge_service import KnowledgeService


def _fresh_service(monkeypatch, knowledge_path):
    """Return a fresh KnowledgeService pointed at a specific knowledge file."""
    monkeypatch.setattr(
        "app.services.knowledge_service.settings",
        SimpleNamespace(mudra_knowledge_path=knowledge_path),
    )
    return KnowledgeService()


def _write_knowledge(tmp_path, payload):
    path = tmp_path / "mudra_knowledge.json"
    path.write_text(payload, encoding="utf-8")
    return path


# ----------------------------------------------------------------------
# Known / unknown grounding
# ----------------------------------------------------------------------

def test_known_mudra_is_grounded(tmp_path, monkeypatch):
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    knowledge = service.ground_mudra("Pataka")

    assert knowledge is not None
    assert knowledge["meaning"] == "Flag / banner"
    assert knowledge["status"] == "curated"


def test_unknown_mudra_is_unresolved(tmp_path, monkeypatch):
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    assert service.ground_mudra("NotAMudra") is None


def test_pending_research_mudra_is_not_grounded(tmp_path, monkeypatch):
    path = _write_knowledge(
        tmp_path,
        '{"Aralam": {"meaning": null, "usage": [], "associated_bhava": [], "source": null, "status": "pending_research"}}',
    )
    service = _fresh_service(monkeypatch, path)

    assert service.ground_mudra("Aralam") is None


# ----------------------------------------------------------------------
# Malformed / missing knowledge file
# ----------------------------------------------------------------------

def test_missing_knowledge_file_returns_no_grounding(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.json"
    service = _fresh_service(monkeypatch, missing)

    assert service.ground_mudra("Pataka") is None
    assert service.load_error() is not None


def test_malformed_knowledge_file_returns_no_grounding(tmp_path, monkeypatch):
    path = _write_knowledge(tmp_path, "{not valid json")
    service = _fresh_service(monkeypatch, path)

    assert service.ground_mudra("Pataka") is None
    assert service.load_error() is not None


def test_non_object_knowledge_file_returns_no_grounding(tmp_path, monkeypatch):
    path = _write_knowledge(tmp_path, "[1, 2, 3]")
    service = _fresh_service(monkeypatch, path)

    assert service.ground_mudra("Pataka") is None
    assert service.load_error() is not None


# ----------------------------------------------------------------------
# Evidence assembly
# ----------------------------------------------------------------------

def test_build_evidence_grounds_known_and_unresolves_unknown(tmp_path, monkeypatch):
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    result = {
        "mudra": {
            "detections": [
                {"name": "Pataka", "confidence": 0.9},
                {"name": "UnknownMudra", "confidence": 0.7},
            ]
        },
        "bhava": {"dominant_emotion": "Happy", "confidence": 0.8},
        "pose": {"primary_pose": "Devi", "confidence": 0.6},
    }

    evidence = service.build_evidence(result)

    assert len(evidence["grounded"]) == 1
    assert evidence["grounded"][0]["label"] == "Pataka"
    assert evidence["grounded"][0]["detail"] == "Flag / banner"
    assert evidence["grounded"][0]["category"] == "grounded"
    assert evidence["grounded"][0]["verification_status"] == "partially_verified"
    assert evidence["grounded"][0]["source_references"] == ["Abhinaya Darpanam"]

    assert len(evidence["unresolved"]) == 1
    assert evidence["unresolved"][0]["label"] == "UnknownMudra"
    assert evidence["unresolved"][0]["category"] == "unresolved"

    assert len(evidence["detected"]) == 2
    assert evidence["detected"][0]["label"] == "Happy facial expression detected"
    assert evidence["detected"][1]["label"] == "Devi pose detected"

    assert evidence["interpreted"] == []


def test_build_evidence_schema_compatibility(tmp_path, monkeypatch):
    """The evidence object must match the frontend contract keys exactly."""
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    evidence = service.build_evidence({"mudra": {"detections": []}})

    assert set(evidence.keys()) == {"grounded", "detected", "unresolved", "interpreted"}
    for key in ("grounded", "detected", "unresolved", "interpreted"):
        assert isinstance(evidence[key], list)


def test_build_evidence_empty_result(tmp_path, monkeypatch):
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    evidence = service.build_evidence({})

    assert evidence == {"grounded": [], "detected": [], "unresolved": [], "interpreted": []}


# ----------------------------------------------------------------------
# Duplicate / consecutive mudra events
# ----------------------------------------------------------------------

def test_build_evidence_deduplicates_consecutive_events(tmp_path, monkeypatch):
    """Consecutive identical mudra events must collapse to one grounded item."""
    path = _write_knowledge(
        tmp_path,
        '{"Pataka": {"meaning": "Flag / banner", "usage": [], "associated_bhava": [], "source": "Abhinaya Darpanam", "status": "curated"}}',
    )
    service = _fresh_service(monkeypatch, path)

    result = {
        "mudra": {
            "detections": [
                {"name": "Pataka", "confidence": 0.9},
                {"name": "Pataka", "confidence": 0.8},
                {"name": "Pataka", "confidence": 0.7},
            ]
        }
    }

    evidence = service.build_evidence(result)

    assert len(evidence["grounded"]) == 1
    assert evidence["grounded"][0]["label"] == "Pataka"
    assert len(evidence["unresolved"]) == 0