"""Explicit endpoint for technical-only audio evidence extraction."""
from fastapi import APIRouter

from app.services.audio_evidence_service import extract_audio_evidence
from app.services.upload_service import get_uploaded_video_path

router = APIRouter(prefix="/api", tags=["Technical Evidence"])


@router.post("/videos/{video_id}/audio-evidence")
def extract_audio(video_id: str) -> dict:
    return extract_audio_evidence(video_id, get_uploaded_video_path(video_id))
