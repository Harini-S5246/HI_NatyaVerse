"""Validated Mudra knowledge retrieval and legacy evidence assembly."""
from __future__ import annotations

import logging
import math
import unicodedata
from pathlib import Path
from threading import Lock
from typing import Any

from jsonschema import Draft202012Validator

from app.config import settings
from app.utils.json_utils import load_json

logger = logging.getLogger(__name__)

CURATED_STATUS = "curated"
KNOWLEDGE_SCHEMA_VERSION = "2.0"
KNOWLEDGE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "knowledge"
    / "mudra_knowledge.schema.json"
)
MINIMUM_RELIABLE_RECOGNITION_CONFIDENCE = 0.5
VERIFICATION_STATUSES = {
    "verified",
    "partially_verified",
    "pending_research",
    "unverified",
}


def is_reliable_recognition_confidence(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and MINIMUM_RELIABLE_RECOGNITION_CONFIDENCE <= value <= 1
    )


def normalize_label(label: str) -> str:
    """Normalize labels for matching without creating aliases."""
    return "".join(char for char in unicodedata.normalize("NFKC", label).casefold() if char.isalnum())


def _legacy_entry(label: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Convert the original label-keyed JSON format without adding claims."""
    normalized = normalize_label(label)
    if not normalized:
        raise ValueError(f"Invalid legacy Mudra label: {label!r}")
    legacy_status = entry.get("status")
    meaning = entry.get("meaning")
    claims: list[dict[str, Any]] = []
    status = "pending_research"
    if legacy_status == CURATED_STATUS and isinstance(meaning, str) and meaning.strip():
        status = "partially_verified"
        sources = []
        source = entry.get("source")
        if isinstance(source, str) and source.strip():
            sources.append({"reference": source.strip(), "bibliographic_details": None})
        claims.append({
            "claim_id": f"claim-{normalized}-namesake",
            "concept_id": None,
            "descriptions": {"en": meaning.strip()},
            "context_conditions": [],
            "usage_conditions": [
                item for item in entry.get("usage", []) if isinstance(item, str)
            ],
            "verification_status": status,
            "sources": sources,
            "uncertainty_notes": [
                "Legacy project-curated namesake only; source details are incomplete."
            ],
        })
    return {
        "mudra_id": f"mudra-{normalized}",
        "canonical_name": label,
        "normalized_label": normalized,
        "approved_aliases": [],
        "knowledge_status": status,
        "meaning_claims": claims,
        "uncertainty_notes": [],
        "legacy_status": legacy_status,
        "legacy_meaning": meaning,
        "legacy_usage": entry.get("usage", []),
        "legacy_associated_bhava": entry.get("associated_bhava", []),
        "legacy_source": entry.get("source"),
    }


def _validate_structured_document(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or raw.get("schema_version") != KNOWLEDGE_SCHEMA_VERSION:
        raise ValueError(f"Knowledge schema_version must be {KNOWLEDGE_SCHEMA_VERSION}.")
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict) or not all(
        isinstance(metadata.get(field), str) and metadata[field].strip()
        for field in ("description", "curation_status", "curation_note")
    ):
        raise ValueError("Knowledge metadata is incomplete.")
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Knowledge entries must be an array.")

    validated: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    seen_claim_ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{prefix} must be an object.")
        if not {
            "mudra_id",
            "canonical_name",
            "normalized_label",
            "approved_aliases",
            "knowledge_status",
            "meaning_claims",
            "uncertainty_notes",
        }.issubset(entry):
            raise ValueError(f"{prefix} is missing required fields.")
        mudra_id = entry.get("mudra_id")
        name = entry.get("canonical_name")
        normalized = entry.get("normalized_label")
        if not isinstance(mudra_id, str) or not mudra_id.strip() or mudra_id in seen_ids:
            raise ValueError(f"{prefix}.mudra_id must be unique and non-empty.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.canonical_name must be non-empty.")
        if not isinstance(normalized, str) or normalized != normalize_label(name):
            raise ValueError(f"{prefix}.normalized_label does not match canonical_name.")
        status = entry.get("knowledge_status")
        if status not in VERIFICATION_STATUSES:
            raise ValueError(f"{prefix}.knowledge_status is invalid.")
        aliases = entry.get("approved_aliases")
        claims = entry.get("meaning_claims")
        if not isinstance(aliases, list) or not all(isinstance(item, str) and item.strip() for item in aliases):
            raise ValueError(f"{prefix}.approved_aliases must contain non-empty strings.")
        if not isinstance(claims, list):
            raise ValueError(f"{prefix}.meaning_claims must be an array.")
        for claim_index, claim in enumerate(claims):
            claim_prefix = f"{prefix}.meaning_claims[{claim_index}]"
            if not isinstance(claim, dict):
                raise ValueError(f"{claim_prefix} must be an object.")
            if not {
                "claim_id",
                "concept_id",
                "descriptions",
                "context_conditions",
                "usage_conditions",
                "verification_status",
                "sources",
                "uncertainty_notes",
            }.issubset(claim):
                raise ValueError(f"{claim_prefix} is missing required fields.")
            if (
                not isinstance(claim.get("claim_id"), str)
                or not claim["claim_id"].strip()
                or claim["claim_id"] in seen_claim_ids
            ):
                raise ValueError(f"{claim_prefix}.claim_id must be unique and non-empty.")
            if claim.get("concept_id") is not None and not isinstance(claim["concept_id"], str):
                raise ValueError(f"{claim_prefix}.concept_id must be a string or null.")
            claim_status = claim.get("verification_status")
            if claim_status not in VERIFICATION_STATUSES:
                raise ValueError(f"{claim_prefix}.verification_status is invalid.")
            descriptions = claim.get("descriptions")
            conditions = claim.get("context_conditions")
            usages = claim.get("usage_conditions")
            sources = claim.get("sources")
            if not isinstance(descriptions, dict) or not descriptions or not all(
                isinstance(locale, str) and isinstance(text, str) and text.strip()
                for locale, text in descriptions.items()
            ):
                raise ValueError(f"{claim_prefix}.descriptions must map locales to non-empty text.")
            if not isinstance(conditions, list) or not all(
                isinstance(item, dict)
                and isinstance(item.get("key"), str)
                and item["key"].strip()
                and isinstance(item.get("value"), str)
                and item["value"].strip()
                for item in conditions
            ):
                raise ValueError(f"{claim_prefix}.context_conditions are invalid.")
            if not isinstance(usages, list) or not all(isinstance(item, str) for item in usages):
                raise ValueError(f"{claim_prefix}.usage_conditions must be strings.")
            if not isinstance(sources, list) or not all(
                isinstance(source, dict)
                and isinstance(source.get("reference"), str)
                and source["reference"].strip()
                and "bibliographic_details" in source
                and (
                    source.get("bibliographic_details") is None
                    or isinstance(source.get("bibliographic_details"), dict)
                )
                for source in sources
            ):
                raise ValueError(f"{claim_prefix}.sources are invalid.")
            for source in sources:
                details = source["bibliographic_details"]
                if isinstance(details, dict) and any(
                    key in details and details[key] is not None and not isinstance(details[key], str)
                    for key in ("author", "edition", "page", "url")
                ):
                    raise ValueError(f"{claim_prefix}.sources bibliographic details are invalid.")
            if not isinstance(claim.get("uncertainty_notes", []), list):
                raise ValueError(f"{claim_prefix}.uncertainty_notes must be an array.")
            if not all(isinstance(note, str) for note in claim.get("uncertainty_notes", [])):
                raise ValueError(f"{claim_prefix}.uncertainty_notes must contain strings.")
            if status in {"pending_research", "unverified"} and claim_status in {
                "verified",
                "partially_verified",
            }:
                raise ValueError(f"{claim_prefix} exceeds its entry verification status.")
            seen_claim_ids.add(claim["claim_id"])
        if not isinstance(entry.get("uncertainty_notes", []), list):
            raise ValueError(f"{prefix}.uncertainty_notes must be an array.")
        if not all(isinstance(note, str) for note in entry.get("uncertainty_notes", [])):
            raise ValueError(f"{prefix}.uncertainty_notes must contain strings.")
        seen_ids.add(mudra_id)
        validated[mudra_id] = entry
    return validated


class KnowledgeService:
    """Lazy, thread-safe access to versioned and legacy Mudra knowledge."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, dict[str, Any]] | None = None
        self._load_error: str | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._entries is not None:
            return self._entries
        with self._lock:
            if self._entries is not None:
                return self._entries
            path = settings.mudra_knowledge_path
            if not path or not path.is_file():
                self._load_error = f"Mudra knowledge base is missing: {path}"
                logger.error(self._load_error)
                return {}
            try:
                raw = load_json(path)
                if isinstance(raw, dict) and raw.get("schema_version") == KNOWLEDGE_SCHEMA_VERSION:
                    schema = load_json(KNOWLEDGE_SCHEMA_PATH)
                    Draft202012Validator.check_schema(schema)
                    Draft202012Validator(schema).validate(raw)
                    entries = _validate_structured_document(raw)
                elif (
                    isinstance(raw, dict)
                    and raw.get("schema_version") in (None, "1.0")
                    and "entries" not in raw
                    and "metadata" not in raw
                ):
                    entries = {
                        f"mudra-{normalize_label(label)}": _legacy_entry(label, entry)
                        for label, entry in raw.items()
                        if label != "_metadata" and isinstance(label, str) and isinstance(entry, dict)
                    }
                    if not entries:
                        raise ValueError("Legacy Mudra knowledge base contains no entries.")
                else:
                    raise ValueError("Mudra knowledge base must be a JSON object.")
            except Exception as exc:
                self._load_error = f"Mudra knowledge base is invalid or could not be read: {exc}"
                logger.exception(self._load_error)
                return {}
            self._entries = entries
            return entries

    def load_error(self) -> str | None:
        self._load()
        return self._load_error

    def is_available(self) -> bool:
        return self._load_error is None and bool(self._load())

    def retrieve_mudra(
        self, label: str, *, context: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Resolve a recognized label and return only source-backed applicable claims."""
        entries = self._load()
        if self._load_error is not None:
            return {"status": "knowledge_unavailable", "reason": self._load_error}
        if not isinstance(label, str) or not label.strip():
            return {"status": "invalid_label", "reason": "Mudra label is empty or invalid."}
        normalized = normalize_label(label)
        matches = []
        for entry in entries.values():
            candidate_labels = [entry["canonical_name"], *entry["approved_aliases"]]
            if any(normalize_label(candidate) == normalized for candidate in candidate_labels):
                matches.append(entry)
        if not matches:
            return {"status": "unknown_label", "reason": "No matching Mudra entry is available."}
        if len(matches) > 1:
            return {"status": "ambiguous_label", "reason": "The label matches multiple Mudra entries."}
        entry = matches[0]
        base = {
            "mudra_id": entry["mudra_id"],
            "canonical_name": entry["canonical_name"],
            "normalized_label": entry["normalized_label"],
            "matched_label": label,
            "knowledge_status": entry["knowledge_status"],
        }
        claims = entry["meaning_claims"]
        if not claims:
            return {**base, "status": entry["knowledge_status"], "reason": "No meaning claim is available."}

        applicable = []
        context_blocked = False
        for claim in claims:
            conditions = claim["context_conditions"]
            if conditions and (
                context is None
                or not all(context.get(item["key"]) == item["value"] for item in conditions)
            ):
                context_blocked = True
                continue
            applicable.append(claim)
        if not applicable:
            return {
                **base,
                "status": "context_required" if context_blocked else "meaning_unavailable",
                "reason": "No claim has a satisfied context condition." if context_blocked else "No applicable meaning claim is available.",
            }
        if len(applicable) > 1:
            return {**base, "status": "ambiguous_meaning", "reason": "Multiple meaning claims are equally applicable."}
        claim = applicable[0]
        if claim["verification_status"] in {"pending_research", "unverified"}:
            return {
                **base,
                "status": claim["verification_status"],
                "reason": "The meaning claim is not verified for cultural retrieval.",
            }
        if not claim["sources"]:
            return {
                **base,
                "status": "missing_source_reference",
                "reason": "The claim has no source reference and cannot be returned as cultural knowledge.",
            }
        return {
            **base,
            "status": claim["verification_status"],
            "claim": claim,
            "reason": None,
        }

    def ground_mudra(self, label: str) -> dict[str, Any] | None:
        """Legacy lookup shape retained for existing services."""
        retrieval = self.retrieve_mudra(label)
        if retrieval.get("status") not in {"verified", "partially_verified"}:
            return None
        claim = retrieval["claim"]
        description = claim["descriptions"].get("en")
        if not description:
            description = next(iter(claim["descriptions"].values()), None)
        return {
            "meaning": description,
            "usage": claim["usage_conditions"],
            "associated_bhava": [],
            "source": claim["sources"][0]["reference"],
            "source_references": [source["reference"] for source in claim["sources"]],
            "status": CURATED_STATUS,
            "knowledge_status": retrieval["status"],
            "verification_status": claim["verification_status"],
            "claim_id": claim["claim_id"],
            "uncertainty_notes": claim["uncertainty_notes"],
        }

    def build_cultural_evidence(
        self,
        mudra_result: dict[str, Any],
        *,
        video_id: str,
        analysis_id: str,
        alignment: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve per-segment claims; alignment is copied only as observation metadata."""
        if mudra_result.get("video_id") not in (None, video_id):
            raise ValueError("Mudra result belongs to a different video.")
        if mudra_result.get("analysis_id") not in (None, analysis_id):
            raise ValueError("Mudra result belongs to a different analysis.")
        sequence = mudra_result.get("temporal_sequence")
        if not isinstance(sequence, dict):
            return [{
                "video_id": video_id,
                "analysis_id": analysis_id,
                "segment_id": None,
                "mudra_label": None,
                "recognition_confidence": None,
                "knowledge_status": "temporal_sequence_unavailable",
                "reason": "Phase 1 temporal Mudra segments are unavailable.",
                "claim_id": None,
                "claim": None,
                "source_references": [],
                "verification_status": None,
            }]
        if sequence.get("video_id") not in (None, video_id):
            raise ValueError("Mudra temporal sequence belongs to a different video.")
        if sequence.get("analysis_id") not in (None, analysis_id):
            raise ValueError("Mudra temporal sequence belongs to a different analysis.")
        segments = sequence.get("segments")
        if not isinstance(segments, list):
            segments = []
        if not segments:
            return [{
                "video_id": video_id,
                "analysis_id": analysis_id,
                "segment_id": None,
                "mudra_label": None,
                "recognition_confidence": None,
                "knowledge_status": "no_valid_mudra_segments",
                "reason": "The temporal sequence contains no valid Mudra segments.",
                "claim_id": None,
                "claim": None,
                "source_references": [],
                "verification_status": None,
            }]

        alignment_by_segment = {}
        if isinstance(alignment, dict):
            for item in alignment.get("alignments", []):
                if isinstance(item, dict) and item.get("mudra_segment_id"):
                    alignment_by_segment[item["mudra_segment_id"]] = item

        evidence = []
        for segment in segments:
            if not isinstance(segment, dict):
                evidence.append({
                    "video_id": video_id,
                    "analysis_id": analysis_id,
                    "segment_id": None,
                    "mudra_label": None,
                    "recognition_confidence": None,
                    "knowledge_status": "invalid_temporal_segment",
                    "reason": "Temporal sequence contains a malformed segment.",
                    "claim_id": None,
                    "claim": None,
                    "source_references": [],
                    "verification_status": None,
                })
                continue
            segment_video_id = segment.get("video_id")
            segment_analysis_id = segment.get("analysis_id")
            if segment_video_id not in (None, video_id):
                raise ValueError("Mudra segment belongs to a different video.")
            if segment_analysis_id not in (None, analysis_id):
                raise ValueError("Mudra segment belongs to a different analysis.")
            label = segment.get("mudra_label")
            confidence_data = segment.get("confidence")
            confidence = (
                confidence_data.get("mean")
                if isinstance(confidence_data, dict)
                else confidence_data
            )
            start = segment.get("start_timestamp")
            end = segment.get("end_timestamp")
            valid_interval = (
                isinstance(start, (int, float))
                and not isinstance(start, bool)
                and isinstance(end, (int, float))
                and not isinstance(end, bool)
                and math.isfinite(start)
                and math.isfinite(end)
                and 0 <= start <= end
            )
            reason = None
            retrieval: dict[str, Any]
            if not isinstance(label, str) or not label.strip():
                retrieval = {"status": "invalid_label", "reason": "Mudra segment has no valid label."}
            elif not isinstance(segment.get("segment_id"), str) or not segment["segment_id"].strip() or not valid_interval:
                reason = "The segment identifier or temporal interval is invalid."
                retrieval = {"status": "invalid_temporal_evidence", "reason": reason}
            elif (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not is_reliable_recognition_confidence(confidence)
            ):
                reason = (
                    "Recognition confidence is missing, invalid, or below "
                    f"{MINIMUM_RELIABLE_RECOGNITION_CONFIDENCE}."
                )
                retrieval = {"status": "withheld_low_confidence", "reason": reason}
            else:
                retrieval = self.retrieve_mudra(label)
            segment_id = segment.get("segment_id")
            alignment_item = alignment_by_segment.get(segment_id)
            evidence.append({
                "video_id": video_id,
                "analysis_id": analysis_id,
                "segment_id": segment_id,
                "mudra_label": label,
                "mudra_id": retrieval.get("mudra_id"),
                "normalized_label": retrieval.get("normalized_label"),
                "start_timestamp": start,
                "end_timestamp": end,
                "frame_indices": [
                    item for item in segment.get("frame_indices", [])
                    if isinstance(item, int) and not isinstance(item, bool)
                ] if isinstance(segment.get("frame_indices", []), list) else [],
                "evidence_ids": [
                    item for item in segment.get("supporting_evidence_ids", [])
                    if isinstance(item, str)
                ] if isinstance(segment.get("supporting_evidence_ids", []), list) else [],
                "recognition_confidence": confidence,
                "uncertainty_status": (
                    segment.get("uncertainty_status")
                    if segment.get("uncertainty_status") != "normal"
                    else retrieval.get("status")
                ),
                "knowledge_status": retrieval.get("status"),
                "reason": retrieval.get("reason"),
                "claim_id": retrieval.get("claim", {}).get("claim_id"),
                "claim": retrieval.get("claim"),
                "source_references": [
                    source["reference"]
                    for source in retrieval.get("claim", {}).get("sources", [])
                ],
                "verification_status": retrieval.get("claim", {}).get("verification_status"),
                "alignment_observation": {
                    "alignment_status": alignment_item.get("alignment_status"),
                    "uncertainty_status": alignment_item.get("uncertainty_status"),
                    "expression_observations": alignment_item.get("expression_observations", []),
                    "overlap_duration": alignment_item.get("overlap_duration"),
                    "mudra_coverage_ratio": alignment_item.get("mudra_coverage_ratio"),
                } if alignment_item else None,
            })
        return evidence

    def build_evidence(self, result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Build the existing four-part evidence payload without changing its contract."""
        grounded: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        detected: list[dict[str, Any]] = []
        interpreted: list[dict[str, Any]] = []

        mudra = result.get("mudra", {})
        detections = mudra.get("detections", []) if isinstance(mudra, dict) else []
        seen_labels: set[str] = set()
        for item in detections:
            if not isinstance(item, dict):
                continue
            label = item.get("name")
            if not isinstance(label, str) or not label or label in seen_labels:
                continue
            seen_labels.add(label)
            confidence = item.get("confidence")
            confidence_is_reliable = is_reliable_recognition_confidence(confidence)
            knowledge = self.ground_mudra(label) if confidence_is_reliable else None
            base = {
                "id": f"mudra-{label}",
                "label": label,
                "confidence": confidence,
            }
            if knowledge:
                grounded.append({
                    **base,
                    "category": "grounded",
                    "detail": knowledge["meaning"],
                    "usage": knowledge["usage"],
                    "associated_bhava": knowledge["associated_bhava"],
                    "source": knowledge["source"],
                    "source_references": knowledge["source_references"],
                    "claim_id": knowledge["claim_id"],
                    "knowledge_status": knowledge["verification_status"],
                    "verification_status": knowledge["verification_status"],
                    "uncertainty_notes": knowledge["uncertainty_notes"],
                })
            else:
                unresolved.append({
                    **base,
                    "category": "unresolved",
                    "detail": (
                        "Meaning withheld because recognition confidence is missing, invalid, or below 0.5"
                        if not confidence_is_reliable
                        else "Meaning unavailable in current knowledge base"
                    ),
                })

        bhava = result.get("bhava", {})
        dominant = bhava.get("dominant_emotion") if isinstance(bhava, dict) else None
        if isinstance(dominant, str) and dominant:
            detected.append({
                "id": "bhava-dominant",
                "label": f"{dominant} facial expression detected",
                "category": "detected",
                "confidence": bhava.get("confidence") or bhava.get("bhava_confidence"),
            })
        pose = result.get("pose", {})
        primary_pose = pose.get("primary_pose") if isinstance(pose, dict) else None
        if isinstance(primary_pose, str) and primary_pose:
            detected.append({
                "id": "pose-primary",
                "label": f"{primary_pose} pose detected",
                "category": "detected",
                "confidence": pose.get("confidence") or pose.get("pose_confidence"),
            })
        return {
            "grounded": grounded,
            "detected": detected,
            "unresolved": unresolved,
            "interpreted": interpreted,
        }


knowledge_service = KnowledgeService()


def ground_mudra(label: str) -> dict[str, Any] | None:
    return knowledge_service.ground_mudra(label)


def build_evidence(result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return knowledge_service.build_evidence(result)


def load_error() -> str | None:
    return knowledge_service.load_error()
