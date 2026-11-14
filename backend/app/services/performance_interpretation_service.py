"""Performance interpretation packages for reviewed claims and model observations."""
from __future__ import annotations

from typing import Any

from app.services.narrative_evidence_service import (
    NarrativeEvidenceValidationError,
    validate_narrative_evidence,
)
from app.services.knowledge_service import (
    MINIMUM_RELIABLE_RECOGNITION_CONFIDENCE,
    is_reliable_recognition_confidence,
    knowledge_service,
)
from app.services.verified_narrative_evidence_service import validate_verified_narrative_evidence

SCHEMA_VERSION = "1.0.0"
_MODALITIES = {"pose", "audio"}


class PerformanceInterpretationValidationError(ValueError):
    """Raised when a package would contain an unsupported interpretation."""


def _evidence_from_annotation(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project provenance fields without changing supplied values."""
    return [
        {
            "source": item["source"],
            "source_reference": item["source_reference"],
            "confidence": item["confidence"],
        }
        for item in items
    ]


def _mode_evidence(mode: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "source": mode["source"],
        "source_reference": mode["source_reference"],
        "confidence": mode["confidence"],
    }]


def _validate_recorded_evidence(items: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise PerformanceInterpretationValidationError(f"{field} must be a non-empty evidence list.")
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise PerformanceInterpretationValidationError(f"{field}[{index}] must be an object.")
        source = item.get("source")
        reference = item.get("source_reference")
        confidence = item.get("confidence")
        if not isinstance(source, str) or not source.strip() or not isinstance(reference, str) or not reference.strip():
            raise PerformanceInterpretationValidationError(f"{field}[{index}] requires source and source_reference.")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise PerformanceInterpretationValidationError(f"{field}[{index}].confidence must be between 0 and 1.")
        clean.append({"source": source, "source_reference": reference, "confidence": confidence})
    return clean


def _mudra_knowledge_observation(label: str, confidence: Any) -> dict[str, Any]:
    if not is_reliable_recognition_confidence(confidence):
        return {
            "label": label,
            "meaning": None,
            "grounding": "unresolved",
            "knowledge_status": "withheld_low_confidence",
            "verification_status": None,
            "claim_id": None,
            "source_references": [],
            "uncertainty_notes": [],
            "uncertainty_reason": (
                "Recognition confidence is missing, invalid, or below "
                f"{MINIMUM_RELIABLE_RECOGNITION_CONFIDENCE}; cultural meaning was withheld."
            ),
            "recognition_confidence": confidence,
        }

    retrieval = knowledge_service.retrieve_mudra(label)
    claim = retrieval.get("claim")
    descriptions = claim.get("descriptions", {}) if isinstance(claim, dict) else {}
    meaning = (
        descriptions.get("en") or next(iter(descriptions.values()), None)
        if isinstance(descriptions, dict)
        else None
    )
    has_meaning = (
        retrieval.get("status") in {"verified", "partially_verified"}
        and isinstance(meaning, str)
        and bool(meaning.strip())
        and isinstance(claim, dict)
    )
    if not has_meaning:
        return {
            "label": label,
            "meaning": None,
            "grounding": "unresolved",
            "knowledge_status": retrieval.get("status"),
            "verification_status": None,
            "claim_id": None,
            "source_references": [],
            "uncertainty_notes": [],
            "uncertainty_reason": retrieval.get("reason"),
            "recognition_confidence": confidence,
        }

    return {
        "label": label,
        "meaning": meaning,
        "grounding": "curated",
        "knowledge_status": retrieval["status"],
        "verification_status": claim["verification_status"],
        "claim_id": claim["claim_id"],
        "source_references": [
            source["reference"]
            for source in claim["sources"]
            if isinstance(source, dict) and isinstance(source.get("reference"), str)
        ],
        "uncertainty_notes": claim["uncertainty_notes"],
        "uncertainty_reason": retrieval.get("reason"),
        "recognition_confidence": confidence,
    }


def _recorded_observation_events(recorded_observations: Any) -> list[dict[str, Any]]:
    """Render observed facts with fixed, non-narrative wording only."""
    if recorded_observations is None:
        return []
    if not isinstance(recorded_observations, dict):
        raise PerformanceInterpretationValidationError("recorded_observations must be an object.")
    allowed = {"mudra", "bhava", "unavailable_modalities"}
    unexpected = set(recorded_observations) - allowed
    if unexpected:
        raise PerformanceInterpretationValidationError("Recorded observations contain unsupported narrative fields.")
    events: list[dict[str, Any]] = []
    for index, item in enumerate(recorded_observations.get("mudra", []) or []):
        if (
            not isinstance(item, dict)
            or set(item) - {"label", "meaning", "evidence", "recognition_confidence"}
        ):
            raise PerformanceInterpretationValidationError("A Mudra observation contains unsupported fields.")
        label = item.get("label")
        if (
            not isinstance(label, str)
            or not label.strip()
            or not isinstance(item.get("meaning"), str)
            or not item["meaning"].strip()
        ):
            raise PerformanceInterpretationValidationError("Mudra observation requires a label and meaning candidate.")
        confidence = item.get("recognition_confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise PerformanceInterpretationValidationError("Mudra recognition_confidence is invalid.")
        knowledge = _mudra_knowledge_observation(label, confidence)
        evidence = _validate_recorded_evidence(item["evidence"], f"mudra[{index}].evidence")
        meaning = knowledge["meaning"]
        if meaning:
            verification = knowledge["verification_status"].replace("_", " ")
            statement = (
                f"The model detected {label}, and the knowledge base records a "
                f"{verification} meaning as '{meaning}'."
            )
        else:
            statement = f"The model detected {label}; reliable cultural knowledge is unavailable."
        events.append({
            "event_id": f"recorded-mudra-{index + 1}", "start_time": None, "end_time": None,
            "type": "recorded_model_observation",
            "statement": statement,
            "evidence": evidence,
            "mudra_knowledge": knowledge,
        })
    for index, item in enumerate(recorded_observations.get("bhava", []) or []):
        if not isinstance(item, dict) or set(item) != {"label", "evidence"}:
            raise PerformanceInterpretationValidationError("A Bhava observation may contain only label and evidence.")
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise PerformanceInterpretationValidationError("Bhava observation requires a label.")
        evidence = _validate_recorded_evidence(item["evidence"], f"bhava[{index}].evidence")
        events.append({
            "event_id": f"recorded-bhava-{index + 1}", "start_time": None, "end_time": None,
            "type": "recorded_model_observation",
            "statement": f"Model output recorded facial expression: {label}.",
            "evidence": evidence,
        })
    unavailable = recorded_observations.get("unavailable_modalities", []) or []
    if not isinstance(unavailable, list) or any(item not in _MODALITIES for item in unavailable):
        raise PerformanceInterpretationValidationError("unavailable_modalities may contain only pose and audio.")
    return events


def _verified_narrative_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in record["events"]:
        claims = event
        subject, action = claims["subject"], claims["action"]
        if subject["verification_status"] != "verified" or action["verification_status"] != "verified":
            continue
        statement = f"Verified narrative event: {subject['label']} {action['label']}"
        target = claims["target"]
        if target["verification_status"] == "verified":
            statement += f" {target['label']}"
        statement += "."
        events.append({
            "event_id": event["event_id"], "start_time": event["start_time"], "end_time": event["end_time"],
            "type": "verified_narrative_event", "statement": statement,
            "evidence": _evidence_from_annotation(event["evidence"]),
        })
    return events


def build_performance_interpretation(
    analysis_id: str,
    narrative_evidence: Any,
    *,
    recorded_observations: Any = None,
    for_production: bool = False,
) -> dict[str, Any]:
    """Build a package from sourced evidence; never infer narrative semantics."""
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise PerformanceInterpretationValidationError("analysis_id must be a non-empty string.")
    try:
        record = validate_narrative_evidence(narrative_evidence, for_production=for_production)
    except NarrativeEvidenceValidationError as exc:
        raise PerformanceInterpretationValidationError(str(exc)) from exc

    mode = record["performance_mode"]
    # Validate caller-supplied observations before branching by mode so an
    # unsupported story field can never be silently accepted and ignored.
    observation_events = _recorded_observation_events(recorded_observations)
    limitations = ["Pose evidence is unavailable; no movement evidence is asserted.", "Audio evidence is unavailable; no lyrics are asserted."]
    base = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "source_type": "synthetic_test_fixture" if record["source_type"] == "synthetic_test_fixture" else "curated_annotation",
        "production_eligible": record["production_eligible"],
        "performance_mode": mode,
        "limitations": limitations,
    }
    if mode["label"] == "unknown":
        return {**base, "interpretation_status": "unavailable", "summary": "Interpretation unavailable: performance mode is unknown.", "events": []}

    mode_event = {
        "event_id": "performance-mode", "start_time": None, "end_time": None,
        "type": "verified_performance_event",
        "statement": f"Performance mode is verified as {mode['label'].replace('_', ' ')}.",
        "evidence": _mode_evidence(mode),
    }
    if mode["label"] == "pure_dance":
        return {**base, "interpretation_status": "available", "summary": "Verified performance mode: pure dance.", "events": [mode_event, *observation_events]}

    events = _verified_narrative_events(record)
    if not events:
        return {**base, "interpretation_status": "unavailable", "summary": "Interpretation unavailable: no verified narrative events are available.", "events": []}
    return {**base, "interpretation_status": "available", "summary": "Verified narrative event sequence available for later story generation.", "events": events}


def build_from_verified_narrative_evidence(analysis_id: str, artifact: Any) -> dict[str, Any]:
    """Build a production package from explicit evidence, never from model artifacts."""
    record = validate_verified_narrative_evidence(artifact, expected_analysis_id=analysis_id)
    mode = record["performance_mode"]
    mode_evidence = [{
        "source": mode["source"]["reference"],
        "source_reference": mode["provenance"]["source_reference"],
        "confidence": mode["provenance"]["verification_confidence"],
    }]
    base = {
        "schema_version": SCHEMA_VERSION, "analysis_id": analysis_id, "video_id": analysis_id,
        "source_type": "curated_annotation", "production_eligible": True,
        "performance_mode": {
            "label": mode["label"], "verification_status": "verified",
            "source": mode["source"]["reference"], "source_reference": mode["provenance"]["source_reference"],
            "confidence": mode["provenance"]["verification_confidence"],
        },
        "limitations": [
            "Only independently verified narrative evidence is included.",
            "Model observations, knowledge-base meanings, fusion timing, pose, and audio evidence are excluded.",
        ],
        "evidence_coverage": {
            "eligible_verified_records": len(record["records"]),
            "excluded_model_or_technical_evidence": True,
        },
    }
    if mode["label"] == "pure_dance":
        return {**base, "interpretation_status": "available", "summary": "Verified performance mode: pure dance.", "events": [{
            "event_id": "performance-mode", "start_time": None, "end_time": None,
            "type": "verified_performance_event", "statement": "Performance mode is verified as pure dance.", "evidence": mode_evidence,
        }]}
    events = [{
        "event_id": item["evidence_id"],
        "start_time": item["span"]["start_time"] if item["span"] else None,
        "end_time": item["span"]["end_time"] if item["span"] else None,
        "type": "verified_narrative_event", "statement": item["statement"],
        "evidence": [{
            "source": item["source"]["reference"],
            "source_reference": item["provenance"]["source_reference"],
            "confidence": item["provenance"]["verification_confidence"],
        }],
    } for item in record["records"]]
    return {**base, "interpretation_status": "available", "summary": "Explicitly verified narrative event sequence available for story generation.", "events": events}


def validate_performance_interpretation(package: Any, *, for_production: bool = False) -> dict[str, Any]:
    """Validate output provenance and prevent synthetic output in production."""
    if not isinstance(package, dict) or package.get("schema_version") != SCHEMA_VERSION:
        raise PerformanceInterpretationValidationError(f"schema_version must be {SCHEMA_VERSION}.")
    required = {"analysis_id", "video_id", "source_type", "production_eligible", "performance_mode", "interpretation_status", "summary", "events", "limitations"}
    if not required.issubset(package):
        raise PerformanceInterpretationValidationError("Performance interpretation package is incomplete.")
    if not all(isinstance(package[field], str) and package[field].strip() for field in ("analysis_id", "video_id", "summary")):
        raise PerformanceInterpretationValidationError("Package identifiers and summary must be non-empty strings.")
    if package["source_type"] not in {"curated_annotation", "model_analysis", "synthetic_test_fixture"} or not isinstance(package["production_eligible"], bool):
        raise PerformanceInterpretationValidationError("Package provenance is invalid.")
    mode = package["performance_mode"]
    if not isinstance(mode, dict) or mode.get("label") not in {"pure_dance", "narrative_dance", "evidence_based", "unknown"}:
        raise PerformanceInterpretationValidationError("Package performance mode is invalid.")
    if mode["label"] == "evidence_based" and (
        package["source_type"] != "model_analysis"
        or mode.get("verification_status") != "unverified"
    ):
        raise PerformanceInterpretationValidationError("Evidence-based interpretation must retain its unverified model provenance.")
    if package["source_type"] == "model_analysis" and mode["label"] != "evidence_based":
        raise PerformanceInterpretationValidationError("Model predictions cannot be represented as a verified performance mode.")
    if package["interpretation_status"] not in {"available", "unavailable"} or not isinstance(package["events"], list):
        raise PerformanceInterpretationValidationError("Package interpretation status or events are invalid.")
    if not isinstance(package["limitations"], list) or not all(isinstance(item, str) and item.strip() for item in package["limitations"]):
        raise PerformanceInterpretationValidationError("Package limitations are invalid.")
    if for_production and (package.get("source_type") == "synthetic_test_fixture" or not package.get("production_eligible")):
        raise PerformanceInterpretationValidationError("Synthetic or non-production interpretation cannot be used in production.")
    event_ids: set[str] = set()
    for event in package["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("event_id"), str) or not event["event_id"].strip() or not isinstance(event.get("statement"), str) or not event["statement"].strip():
            raise PerformanceInterpretationValidationError("Interpretation event requires a statement.")
        if event["event_id"] in event_ids:
            raise PerformanceInterpretationValidationError("Interpretation event IDs must be unique.")
        event_ids.add(event["event_id"])
        if event.get("type") not in {"verified_performance_event", "verified_narrative_event", "recorded_model_observation"}:
            raise PerformanceInterpretationValidationError("Interpretation event type is invalid.")
        start, end = event.get("start_time"), event.get("end_time")
        if start is not None and (not isinstance(start, (int, float)) or isinstance(start, bool) or start < 0):
            raise PerformanceInterpretationValidationError("Interpretation event start_time is invalid.")
        if end is not None and (not isinstance(end, (int, float)) or isinstance(end, bool) or end < 0 or (start is not None and end < start)):
            raise PerformanceInterpretationValidationError("Interpretation event end_time is invalid.")
        event_evidence = _validate_recorded_evidence(event.get("evidence"), f"event {event.get('event_id', '')} evidence")
        mudra_knowledge = event.get("mudra_knowledge")
        if mudra_knowledge is not None:
            if not isinstance(mudra_knowledge, dict):
                raise PerformanceInterpretationValidationError("Mudra knowledge metadata is invalid.")
            confidence = mudra_knowledge.get("recognition_confidence")
            meaning = mudra_knowledge.get("meaning")
            if confidence is not None and (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0 <= confidence <= 1
            ):
                raise PerformanceInterpretationValidationError("Mudra recognition confidence is invalid.")
            if meaning is None:
                if (
                    mudra_knowledge.get("grounding") != "unresolved"
                    or not isinstance(mudra_knowledge.get("uncertainty_reason"), str)
                    or not mudra_knowledge["uncertainty_reason"].strip()
                ):
                    raise PerformanceInterpretationValidationError("Unresolved Mudra knowledge requires an uncertainty reason.")
            elif (
                not isinstance(meaning, str)
                or not meaning.strip()
                or not is_reliable_recognition_confidence(confidence)
                or mudra_knowledge.get("grounding") != "curated"
                or mudra_knowledge.get("knowledge_status") not in {"verified", "partially_verified"}
                or mudra_knowledge.get("verification_status") != mudra_knowledge.get("knowledge_status")
                or not isinstance(mudra_knowledge.get("claim_id"), str)
                or not mudra_knowledge["claim_id"].strip()
                or not isinstance(mudra_knowledge.get("source_references"), list)
                or not mudra_knowledge["source_references"]
                or any(not isinstance(item, str) or not item.strip() for item in mudra_knowledge["source_references"])
                or not isinstance(mudra_knowledge.get("uncertainty_notes"), list)
                or any(not isinstance(item, str) for item in mudra_knowledge["uncertainty_notes"])
            ):
                raise PerformanceInterpretationValidationError(
                    "Mudra meaning requires reliable confidence, verification status, claim ID, source references, and uncertainty notes."
                )
            if not isinstance(mudra_knowledge.get("label"), str) or not mudra_knowledge["label"].strip():
                raise PerformanceInterpretationValidationError("Mudra knowledge label is required.")
            canonical_knowledge = _mudra_knowledge_observation(
                mudra_knowledge["label"],
                confidence,
            )
            if mudra_knowledge != canonical_knowledge:
                raise PerformanceInterpretationValidationError(
                    "Mudra knowledge claim or provenance does not match the current KnowledgeService record."
                )
        if package["source_type"] == "model_analysis":
            observations = event.get("observations")
            if (
                event.get("type") != "recorded_model_observation"
                or start is None
                or end is None
                or not isinstance(observations, dict)
                or not observations
            ):
                raise PerformanceInterpretationValidationError("Model analysis events require timestamped, structured observations.")
            if set(observations) - {"mudra", "bhava", "pose_context"}:
                raise PerformanceInterpretationValidationError("Model analysis event contains unsupported observation fields.")
            for modality in ("mudra", "bhava"):
                observation = observations.get(modality)
                if observation is None:
                    continue
                if not isinstance(observation, dict) or not isinstance(observation.get("label"), str) or not observation["label"].strip():
                    raise PerformanceInterpretationValidationError(f"Model {modality} observation has no label.")
                confidence = observation.get("confidence")
                if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                    raise PerformanceInterpretationValidationError(f"Model {modality} confidence is invalid.")
                if modality == "mudra":
                    meaning, grounding = observation.get("meaning"), observation.get("grounding")
                    if meaning is not None and (not isinstance(meaning, str) or not meaning.strip()):
                        raise PerformanceInterpretationValidationError("Curated Mudra meaning is invalid.")
                    if grounding not in {"curated", "unresolved"} or (grounding == "curated") != (meaning is not None):
                        raise PerformanceInterpretationValidationError("Mudra grounding does not match its knowledge-base meaning.")
                    if meaning is not None:
                        if not is_reliable_recognition_confidence(confidence):
                            raise PerformanceInterpretationValidationError(
                                "Mudra meaning cannot be included below the recognition-confidence threshold."
                            )
                        verification_status = observation.get("verification_status")
                        source_references = observation.get("source_references")
                        uncertainty_notes = observation.get("uncertainty_notes")
                        if (
                            verification_status not in {"verified", "partially_verified"}
                            or observation.get("knowledge_status") != verification_status
                            or not isinstance(observation.get("claim_id"), str)
                            or not observation["claim_id"].strip()
                            or not isinstance(source_references, list)
                            or not source_references
                            or any(not isinstance(item, str) or not item.strip() for item in source_references)
                            or not isinstance(uncertainty_notes, list)
                            or any(not isinstance(item, str) for item in uncertainty_notes)
                        ):
                            raise PerformanceInterpretationValidationError(
                                "Mudra meaning requires verification status, claim ID, source references, and uncertainty notes."
                            )
                    canonical_knowledge = _mudra_knowledge_observation(
                        observation["label"],
                        confidence,
                    )
                    for field in (
                        "meaning",
                        "grounding",
                        "knowledge_status",
                        "verification_status",
                        "claim_id",
                        "source_references",
                        "uncertainty_notes",
                        "uncertainty_reason",
                    ):
                        if observation.get(field) != canonical_knowledge[field]:
                            raise PerformanceInterpretationValidationError(
                                "Mudra meaning or provenance does not match the current KnowledgeService record."
                            )
            if not any(
                modality in observations
                for modality in ("mudra", "bhava", "pose_context")
            ):
                raise PerformanceInterpretationValidationError("Model analysis event contains no usable observations.")
            if "pose_context" in observations and (
                not isinstance(observations["pose_context"], str)
                or not observations["pose_context"].strip()
            ):
                raise PerformanceInterpretationValidationError("Pose context must be a non-empty observed label.")
            if any(package["analysis_id"] not in item["source_reference"] for item in event_evidence):
                raise PerformanceInterpretationValidationError("Model evidence references must belong to the requested analysis.")
    return package


def _validate_analysis_artifact(analysis_id: str, artifact: Any, name: str) -> dict[str, Any]:
    if (
        not isinstance(artifact, dict)
        or artifact.get("analysis_id") != analysis_id
        or artifact.get("video_id") != analysis_id
        or artifact.get("status") != "completed"
    ):
        raise PerformanceInterpretationValidationError(
            f"{name} result is missing, incomplete, or belongs to a different analysis."
        )
    return artifact


def build_analysis_observation_interpretation(
    analysis_id: str,
    fusion_result: dict,
    mudra_result: dict,
    bhava_result: dict,
    *,
    pose_result: dict[str, Any] | None = None,
    audio_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a cautious interpretation from this analysis's recorded outputs."""
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise PerformanceInterpretationValidationError("analysis_id must be a non-empty string.")
    fusion_result = _validate_analysis_artifact(analysis_id, fusion_result, "Fusion")
    mudra_result = _validate_analysis_artifact(analysis_id, mudra_result, "Mudra")
    bhava_result = _validate_analysis_artifact(analysis_id, bhava_result, "Bhava")
    if pose_result is not None:
        if (
            not isinstance(pose_result, dict)
            or pose_result.get("analysis_id") != analysis_id
            or pose_result.get("video_id") != analysis_id
        ):
            raise PerformanceInterpretationValidationError("Pose result belongs to a different analysis.")
        if not isinstance(pose_result.get("events", []), list):
            raise PerformanceInterpretationValidationError("Pose events must be an array.")
    if audio_result is not None:
        from app.services.audio_evidence_service import validate_audio_evidence

        try:
            validate_audio_evidence(audio_result, expected_analysis_id=analysis_id)
        except ValueError as exc:
            raise PerformanceInterpretationValidationError(str(exc)) from exc

    timeline = fusion_result.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise PerformanceInterpretationValidationError("Fusion timeline contains no actual temporal records.")

    mudra_events = mudra_result.get("mudra_events")
    bhava_events = bhava_result.get("bhava_events")
    if not isinstance(mudra_events, list) or not isinstance(bhava_events, list):
        raise PerformanceInterpretationValidationError("Mudra and Bhava prediction events are required.")

    def modality_supports(
        modality_events: list[Any],
        label_key: str,
        label: str,
        start: float,
        end: float,
    ) -> bool:
        return any(
            isinstance(item, dict)
            and item.get(label_key) == label
            and isinstance(item.get("start_time"), (int, float))
            and isinstance(item.get("end_time"), (int, float))
            and item["start_time"] <= end
            and start <= item["end_time"]
            for item in modality_events
        )

    def validate_confidence(value: Any, field: str) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise PerformanceInterpretationValidationError(f"{field} must be an actual confidence between 0 and 1.")
        return float(value)

    # The Fusion timeline is already grouped by contiguous Mudra/Bhava
    # combinations. Reuse those real temporal boundaries and merge any
    # adjacent duplicate combinations without dropping transitions.
    events: list[dict[str, Any]] = []
    previous_start: float | None = None
    for index, row in enumerate(timeline):
        if not isinstance(row, dict):
            raise PerformanceInterpretationValidationError(f"Fusion timeline row {index} is invalid.")
        start, end = row.get("start_time"), row.get("end_time")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
            or start < 0
            or end < start
            or (previous_start is not None and start < previous_start)
        ):
            raise PerformanceInterpretationValidationError(f"Fusion timeline row {index} has invalid or unordered timestamps.")
        previous_start = float(start)

        mudra_label, bhava_label = row.get("mudra"), row.get("bhava")
        if mudra_label is None and bhava_label is None:
            continue
        if mudra_label is not None and (not isinstance(mudra_label, str) or not mudra_label.strip()):
            raise PerformanceInterpretationValidationError(f"Fusion timeline row {index} has an invalid Mudra label.")
        if bhava_label is not None and (not isinstance(bhava_label, str) or not bhava_label.strip()):
            raise PerformanceInterpretationValidationError(f"Fusion timeline row {index} has an invalid Bhava label.")

        observations: dict[str, Any] = {}
        evidence: list[dict[str, Any]] = []
        if mudra_label:
            if not modality_supports(mudra_events, "mudra", mudra_label, float(start), float(end)):
                raise PerformanceInterpretationValidationError(
                    f"Fusion Mudra at timeline[{index}] is not supported by this analysis's Mudra result."
                )
            mudra_confidence = validate_confidence(row.get("mudra_confidence"), f"timeline[{index}].mudra_confidence")
            observations["mudra"] = {
                "label": mudra_label,
                "confidence": mudra_confidence,
                **_mudra_knowledge_observation(mudra_label, mudra_confidence),
            }
            evidence.append({
                "source": "mudra_model",
                "source_reference": f"mudra:{analysis_id}#timeline[{index}]",
                "confidence": mudra_confidence,
            })
        if bhava_label:
            if not modality_supports(bhava_events, "bhava", bhava_label, float(start), float(end)):
                raise PerformanceInterpretationValidationError(
                    f"Fusion Bhava at timeline[{index}] is not supported by this analysis's Bhava result."
                )
            bhava_confidence = validate_confidence(row.get("bhava_confidence"), f"timeline[{index}].bhava_confidence")
            observations["bhava"] = {"label": bhava_label, "confidence": bhava_confidence}
            evidence.append({
                "source": "bhava_model",
                "source_reference": f"bhava:{analysis_id}#timeline[{index}]",
                "confidence": bhava_confidence,
            })

        pose_context = None
        if pose_result is not None:
            for pose_event in pose_result.get("events", []):
                if not isinstance(pose_event, dict) or pose_event.get("grounding_status") != "supported":
                    continue
                pose_label = pose_event.get("pose_evidence")
                if (
                    isinstance(pose_label, str)
                    and pose_label.strip()
                    and pose_event.get("start_time") == start
                    and pose_event.get("end_time") == end
                ):
                    pose_context = pose_label.strip()
                    confidence = validate_confidence(pose_event.get("confidence"), f"pose_events[{index}].confidence")
                    evidence.append({
                        "source": "pose_model",
                        "source_reference": f"pose:{analysis_id}#{pose_event.get('event_id', index)}",
                        "confidence": confidence,
                    })
                    break
        if pose_context:
            observations["pose_context"] = pose_context

        frame_numbers = [
            frame.get("frame_number")
            for result in (mudra_result, bhava_result)
            for frame in (result.get("frames") or [])
            if isinstance(frame, dict)
            and isinstance(frame.get("frame_number"), int)
            and not isinstance(frame.get("frame_number"), bool)
            and isinstance(frame.get("timestamp"), (int, float))
            and float(start) <= frame["timestamp"] <= float(end)
        ]
        frame_range = [min(frame_numbers), max(frame_numbers)] if frame_numbers else None
        statement_parts = [f"{key}: {value['label']}" for key, value in observations.items() if key in {"mudra", "bhava"}]
        events.append({
            "event_id": f"analysis-segment-{index + 1:04d}",
            "start_time": float(start),
            "end_time": float(end),
            "frame_range": frame_range,
            "type": "recorded_model_observation",
            "statement": f"From {float(start):.2f}s to {float(end):.2f}s, the analysis detected {'; '.join(statement_parts)}.",
            "observations": observations,
            "evidence": evidence,
        })

    if not events:
        raise PerformanceInterpretationValidationError("Fusion timeline contains no usable Mudra or Bhava predictions.")

    limitations = [
        "This is an evidence-based interpretation of model predictions, not a verified account of the original story.",
        "Model predictions may be uncertain; confidence values are preserved with each observation.",
        "Mudra meanings are included only for source-backed verified or partially verified knowledge claims.",
        "Facial-expression labels are generic model outputs, not classical Bhava or Rasa recognition, and do not establish causes or character emotions.",
    ]
    if not any(event.get("observations", {}).get("pose_context") for event in events):
        limitations.append("Pose context is unavailable; no movement claims are asserted.")

    audio_context = None
    if audio_result is not None:
        audio_context = {
            "availability": audio_result["availability"]["audio"],
            "extraction_status": audio_result["extraction"]["status"],
            "narrative_eligible": False,
        }
        limitations.append("Audio evidence is technical-only; no lyrics or audio narrative are asserted.")
    else:
        limitations.append("No audio evidence artifact is available; no lyrics are asserted.")

    package = {
        "schema_version": "1.0.0",
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "source_type": "model_analysis",
        "production_eligible": True,
        "performance_mode": {
            "label": "evidence_based",
            "verification_status": "unverified",
            "source": "fusion_analysis",
            "source_reference": f"fusion:{analysis_id}#timeline",
        },
        "interpretation_status": "available",
        "summary": "Chronological interpretation from stored Mudra and Bhava model predictions.",
        "events": events,
        "limitations": limitations,
        "evidence_coverage": {
            "eligible_verified_records": 0,
            "analysis_observation_events": len(events),
            "total_timeline_rows": len(timeline),
            "excluded_model_or_technical_evidence": True,
        },
    }
    if audio_context is not None:
        package["audio_context"] = audio_context

    return validate_performance_interpretation(package, for_production=True)
