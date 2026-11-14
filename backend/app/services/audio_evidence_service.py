"""Technical-only audio evidence extraction with strict semantic abstention."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.errors import AppError
from app.services.result_service import save_modality_result

SCHEMA_VERSION = "1.0.0"
EXTRACTOR_VERSION = "ffmpeg-stream-copy-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AudioEvidenceValidationError(ValueError):
    """Raised when a technical audio artifact lacks required provenance."""


def _relative_reference(path: Path) -> str:
    """Return a stable project-relative reference, never an absolute path."""
    try:
        return path.resolve().relative_to(settings.results_dir.parent.resolve()).as_posix()
    except ValueError:
        return path.name


def _empty_properties() -> dict[str, Any]:
    return {"duration": None, "timeline_start_time": None, "sample_rate": None, "channels": None, "codec": None, "container": None}


def _base_artifact(analysis_id: str, video_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "source": {"type": "uploaded_video", "reference": _relative_reference(video_path), "version": "upload-service-v1"},
        "availability": {"audio": None, "reason": None},
        "technical_properties": _empty_properties(),
        "extraction": {"status": "pending", "extractor": "ffmpeg", "extractor_version": EXTRACTOR_VERSION, "extracted_at": None, "audio_reference": None},
        "segments": [],
        "production_eligibility": {"status": "technical_only", "narrative_eligible": False},
        "errors": [],
    }


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)


def _is_invokable(executable: Path) -> bool:
    """Confirm a candidate binary can actually be started before using it."""
    if not executable.is_file():
        return False
    try:
        return _run([str(executable), "-version"]).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_executable(executable_name: str, environment_variable: str) -> str | None:
    """Resolve an FFmpeg binary from env, PATH, then project-local tools only."""
    configured_path = os.getenv(environment_variable, "").strip()
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if _is_invokable(candidate):
            return str(candidate)

    path_candidate = shutil.which(executable_name)
    if path_candidate and _is_invokable(Path(path_candidate)):
        return path_candidate

    tools_dir = PROJECT_ROOT / "tools"
    if tools_dir.is_dir():
        for candidate in sorted(tools_dir.glob(f"**/bin/{executable_name}")):
            if _is_invokable(candidate):
                return str(candidate)
    return None


def _ffprobe_path() -> str | None:
    return _resolve_executable("ffprobe.exe" if os.name == "nt" else "ffprobe", "FFPROBE_PATH")


def _ffmpeg_path() -> str | None:
    return _resolve_executable("ffmpeg.exe" if os.name == "nt" else "ffmpeg", "FFMPEG_PATH")


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "N/A") else None
    except (TypeError, ValueError):
        return None


def _probe(video_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    ffprobe = _ffprobe_path()
    if not ffprobe:
        return None, "ffprobe is unavailable; audio availability could not be determined."
    try:
        result = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"ffprobe failed: {type(exc).__name__}."
    if result.returncode:
        return None, f"ffprobe failed: {result.stderr.strip() or 'unknown error'}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, "ffprobe returned invalid metadata."


def _audio_stream(probe: dict[str, Any]) -> dict[str, Any] | None:
    return next((stream for stream in probe.get("streams", []) if isinstance(stream, dict) and stream.get("codec_type") == "audio"), None)


def validate_audio_evidence(artifact: Any, *, expected_analysis_id: str | None = None) -> dict[str, Any]:
    if not isinstance(artifact, dict) or artifact.get("schema_version") != SCHEMA_VERSION:
        raise AudioEvidenceValidationError(f"schema_version must be {SCHEMA_VERSION}.")
    required = {"analysis_id", "video_id", "source", "availability", "technical_properties", "extraction", "segments", "production_eligibility", "errors"}
    if set(artifact) != required | {"schema_version"} or artifact["analysis_id"] != artifact["video_id"]:
        raise AudioEvidenceValidationError("Audio evidence requires matching analysis_id and video_id.")
    if expected_analysis_id and artifact["analysis_id"] != expected_analysis_id:
        raise AudioEvidenceValidationError("Audio evidence belongs to a different analysis.")
    source, extraction = artifact["source"], artifact["extraction"]
    if (
        not isinstance(source, dict)
        or set(source) != {"type", "reference", "version"}
        or source.get("type") != "uploaded_video"
        or not all(isinstance(source.get(key), str) and source[key] for key in ("reference", "version"))
    ):
        raise AudioEvidenceValidationError("Audio evidence source provenance is incomplete.")
    if (
        not isinstance(extraction, dict)
        or set(extraction) != {"status", "extractor", "extractor_version", "extracted_at", "audio_reference"}
        or extraction.get("status") not in {"pending", "extracted", "no_audio", "unavailable", "failed"}
        or extraction.get("extractor") != "ffmpeg"
        or not isinstance(extraction.get("extractor_version"), str)
        or not extraction["extractor_version"]
    ):
        raise AudioEvidenceValidationError("Audio evidence extraction provenance is incomplete.")
    availability = artifact["availability"]
    if not isinstance(availability, dict) or availability.get("audio") not in {True, False, None}:
        raise AudioEvidenceValidationError("Audio availability is invalid.")
    if set(availability) != {"audio", "reason"} or not isinstance(availability.get("reason"), (str, type(None))):
        raise AudioEvidenceValidationError("Audio availability provenance is incomplete.")
    properties = artifact["technical_properties"]
    property_keys = {"duration", "timeline_start_time", "sample_rate", "channels", "codec", "container"}
    if not isinstance(properties, dict) or set(properties) != property_keys:
        raise AudioEvidenceValidationError("Audio technical properties are incomplete.")
    eligibility = artifact["production_eligibility"]
    if eligibility != {"status": "technical_only", "narrative_eligible": False}:
        raise AudioEvidenceValidationError("Raw audio evidence must remain technical_only and non-narrative.")
    if not isinstance(artifact["segments"], list) or not isinstance(artifact["errors"], list):
        raise AudioEvidenceValidationError("Audio evidence segments and errors must be arrays.")
    for segment in artifact["segments"]:
        if not isinstance(segment, dict) or not all(isinstance(segment.get(key), str) and segment[key] for key in ("evidence_id", "audio_reference", "verification_status", "provenance")):
            raise AudioEvidenceValidationError("Audio segment provenance is incomplete.")
        if segment.get("verification_status") != "unknown" or segment.get("production_eligibility") is not False:
            raise AudioEvidenceValidationError("Raw audio segments cannot be semantic or production eligible.")
        if not isinstance(segment.get("start_time"), (int, float)) or not isinstance(segment.get("end_time"), (int, float, type(None))):
            raise AudioEvidenceValidationError("Audio segment timestamps are invalid.")
    if extraction["status"] == "extracted" and (not isinstance(extraction["audio_reference"], str) or not extraction["audio_reference"] or not artifact["segments"]):
        raise AudioEvidenceValidationError("Extracted audio requires an artifact reference and timestamped segment.")
    if extraction["status"] != "extracted" and (extraction["audio_reference"] is not None or artifact["segments"]):
        raise AudioEvidenceValidationError("Unavailable audio must not reference an extracted artifact.")
    return artifact


def extract_audio_evidence(analysis_id: str, video_path: Path) -> dict[str, Any]:
    """Extract a stream-copy artifact, or explicitly abstain when unavailable."""
    if not isinstance(analysis_id, str) or not analysis_id.strip() or not video_path.is_file():
        raise AppError("Uploaded video was not found; audio evidence was not created.", 404, "VIDEO_NOT_FOUND")
    artifact = _base_artifact(analysis_id, video_path)
    probe, probe_error = _probe(video_path)
    if probe_error:
        artifact["availability"] = {"audio": None, "reason": probe_error}
        artifact["extraction"]["status"] = "unavailable"
        artifact["errors"].append(probe_error)
        validate_audio_evidence(artifact, expected_analysis_id=analysis_id)
        save_modality_result(analysis_id, "audio_evidence", artifact)
        return artifact
    stream = _audio_stream(probe or {})
    if stream is None:
        artifact["availability"] = {"audio": False, "reason": "The source video contains no audio stream."}
        artifact["extraction"]["status"] = "no_audio"
        validate_audio_evidence(artifact, expected_analysis_id=analysis_id)
        save_modality_result(analysis_id, "audio_evidence", artifact)
        return artifact

    properties = artifact["technical_properties"]
    properties.update({"duration": _as_float(stream.get("duration") or (probe or {}).get("format", {}).get("duration")), "timeline_start_time": _as_float(stream.get("start_time")), "sample_rate": int(stream["sample_rate"]) if str(stream.get("sample_rate", "")).isdigit() else None, "channels": stream.get("channels") if isinstance(stream.get("channels"), int) else None, "codec": stream.get("codec_name"), "container": (probe or {}).get("format", {}).get("format_name")})
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        artifact["availability"] = {"audio": True, "reason": "Audio stream verified, but ffmpeg is unavailable to extract it."}
        artifact["extraction"]["status"] = "unavailable"
        artifact["errors"].append("ffmpeg is unavailable.")
        validate_audio_evidence(artifact, expected_analysis_id=analysis_id)
        save_modality_result(analysis_id, "audio_evidence", artifact)
        return artifact

    output_path = settings.results_dir / "audio" / f"{analysis_id}.mka"
    temporary_output_path = settings.results_dir / "audio" / f"{analysis_id}.extracting.mka"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run([ffmpeg, "-y", "-copyts", "-i", str(video_path), "-map", "0:a:0", "-c:a", "copy", "-vn", str(temporary_output_path)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = None
        artifact["errors"].append(f"ffmpeg failed: {type(exc).__name__}.")
    if result is None or result.returncode or not temporary_output_path.is_file():
        temporary_output_path.unlink(missing_ok=True)
        artifact["availability"] = {"audio": True, "reason": "Audio stream verified, but extraction failed."}
        artifact["extraction"]["status"] = "failed"
        if result is not None:
            artifact["errors"].append(result.stderr.strip() or "ffmpeg failed without an error message.")
    else:
        os.replace(temporary_output_path, output_path)
        reference = _relative_reference(output_path)
        artifact["availability"] = {"audio": True, "reason": None}
        artifact["extraction"].update({"status": "extracted", "extracted_at": datetime.now(timezone.utc).isoformat(), "audio_reference": reference})
        start = properties["timeline_start_time"] if properties["timeline_start_time"] is not None else 0.0
        end = start + properties["duration"] if properties["duration"] is not None else None
        artifact["segments"] = [{"evidence_id": "audio-stream-0001", "start_time": start, "end_time": end, "audio_reference": reference, "provenance": "source audio stream 0; timestamps preserved with ffmpeg -copyts", "verification_status": "unknown", "production_eligibility": False}]
    validate_audio_evidence(artifact, expected_analysis_id=analysis_id)
    save_modality_result(analysis_id, "audio_evidence", artifact)
    return artifact
