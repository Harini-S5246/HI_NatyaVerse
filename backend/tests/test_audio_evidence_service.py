"""Focused tests for technical-only audio evidence extraction."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import audio_evidence_service


def _configure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(audio_evidence_service, "settings", SimpleNamespace(results_dir=tmp_path / "results"))
    monkeypatch.setattr(audio_evidence_service, "save_modality_result", lambda *_: None)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    return video


def _available_tools(monkeypatch):
    monkeypatch.setattr(audio_evidence_service, "_ffprobe_path", lambda: "/ffprobe")
    monkeypatch.setattr(audio_evidence_service, "_ffmpeg_path", lambda: "/ffmpeg")


def test_audio_stream_is_extracted_with_technical_provenance(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    _available_tools(monkeypatch)

    def run(command):
        if "ffprobe" in command[0]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"streams": [{"codec_type": "audio", "duration": "12.5", "start_time": "0.25", "sample_rate": "48000", "channels": 2, "codec_name": "aac"}], "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"}}), "")
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(audio_evidence_service, "_run", run)
    result = audio_evidence_service.extract_audio_evidence("a-1", video)
    assert result["availability"]["audio"] is True
    assert result["technical_properties"]["sample_rate"] == 48000
    assert result["technical_properties"]["timeline_start_time"] == 0.25
    assert result["segments"][0]["start_time"] == 0.25
    assert result["segments"][0]["verification_status"] == "unknown"
    assert result["production_eligibility"] == {"status": "technical_only", "narrative_eligible": False}


def test_video_without_audio_has_explicit_abstention(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(audio_evidence_service, "_ffprobe_path", lambda: "/ffprobe")
    monkeypatch.setattr(audio_evidence_service, "_run", lambda command: subprocess.CompletedProcess(command, 0, json.dumps({"streams": [{"codec_type": "video"}], "format": {}}), ""))
    result = audio_evidence_service.extract_audio_evidence("a-1", video)
    assert result["availability"] == {"audio": False, "reason": "The source video contains no audio stream."}
    assert result["segments"] == []
    assert result["extraction"]["status"] == "no_audio"


def test_missing_video_fails_without_saving_artifact(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(audio_evidence_service, "save_modality_result", lambda *_: saved.append(True))
    with pytest.raises(AppError, match="not found"):
        audio_evidence_service.extract_audio_evidence("a-1", tmp_path / "missing.mp4")
    assert saved == []


def test_artifact_cannot_cross_analysis_ids(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    artifact = audio_evidence_service._base_artifact("analysis-a", video)
    with pytest.raises(audio_evidence_service.AudioEvidenceValidationError, match="different analysis"):
        audio_evidence_service.validate_audio_evidence(artifact, expected_analysis_id="analysis-b")


def test_extraction_never_reuses_a_stale_audio_file(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    _available_tools(monkeypatch)
    stale = tmp_path / "results" / "audio" / "a-1.mka"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale-audio")

    def run(command):
        if "ffprobe" in command[0]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"streams": [{"codec_type": "audio"}], "format": {}}), "")
        return subprocess.CompletedProcess(command, 1, "", "simulated extraction failure")

    monkeypatch.setattr(audio_evidence_service, "_run", run)
    result = audio_evidence_service.extract_audio_evidence("a-1", video)
    assert result["extraction"]["status"] == "failed"
    assert result["extraction"]["audio_reference"] is None
    assert result["segments"] == []


def test_missing_provenance_is_rejected(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    artifact = audio_evidence_service._base_artifact("a-1", video)
    del artifact["source"]["reference"]
    with pytest.raises(audio_evidence_service.AudioEvidenceValidationError, match="provenance"):
        audio_evidence_service.validate_audio_evidence(artifact)


def test_raw_audio_cannot_become_narrative_evidence(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    artifact = audio_evidence_service._base_artifact("a-1", video)
    artifact["production_eligibility"] = {"status": "narrative", "narrative_eligible": True}
    with pytest.raises(audio_evidence_service.AudioEvidenceValidationError, match="technical_only"):
        audio_evidence_service.validate_audio_evidence(artifact)


def test_project_local_ffmpeg_is_discovered_after_path_lookup_fails(monkeypatch, tmp_path):
    tools_dir = tmp_path / "tools" / "ffmpeg-release" / "nested" / "bin"
    tools_dir.mkdir(parents=True)
    executable = tools_dir / ("ffmpeg.exe" if audio_evidence_service.os.name == "nt" else "ffmpeg")
    executable.write_bytes(b"binary")
    monkeypatch.setattr(audio_evidence_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(audio_evidence_service.shutil, "which", lambda _: None)
    monkeypatch.setattr(audio_evidence_service, "_is_invokable", lambda path: path == executable)
    assert audio_evidence_service._ffmpeg_path() == str(executable)


def test_environment_override_precedes_path_and_project_tools(monkeypatch, tmp_path):
    configured = tmp_path / "configured-ffprobe.exe"
    configured.write_bytes(b"binary")
    monkeypatch.setenv("FFPROBE_PATH", str(configured))
    monkeypatch.setattr(audio_evidence_service.shutil, "which", lambda _: pytest.fail("PATH must not be checked"))
    monkeypatch.setattr(audio_evidence_service, "_is_invokable", lambda path: path == configured)
    assert audio_evidence_service._ffprobe_path() == str(configured)


def test_path_lookup_remains_available_when_no_override_exists(monkeypatch, tmp_path):
    path_tool = tmp_path / ("ffprobe.exe" if audio_evidence_service.os.name == "nt" else "ffprobe")
    path_tool.write_bytes(b"binary")
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr(audio_evidence_service.shutil, "which", lambda _: str(path_tool))
    monkeypatch.setattr(audio_evidence_service, "_is_invokable", lambda path: path == path_tool)
    assert audio_evidence_service._ffprobe_path() == str(path_tool)


def test_missing_ffmpeg_fails_safely_after_audio_is_verified(monkeypatch, tmp_path):
    video = _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(audio_evidence_service, "_ffprobe_path", lambda: "/ffprobe")
    monkeypatch.setattr(audio_evidence_service, "_ffmpeg_path", lambda: None)
    monkeypatch.setattr(audio_evidence_service, "_run", lambda command: subprocess.CompletedProcess(command, 0, json.dumps({"streams": [{"codec_type": "audio"}], "format": {}}), ""))
    result = audio_evidence_service.extract_audio_evidence("a-1", video)
    assert result["availability"]["audio"] is True
    assert result["extraction"]["status"] == "unavailable"
    assert result["extraction"]["audio_reference"] is None
