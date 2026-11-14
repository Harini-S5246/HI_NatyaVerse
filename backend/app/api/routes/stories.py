import logging

from fastapi import APIRouter

from app.api.schemas.story import NarrativeGenerationResponse, StoryRequest
from app.services.story_integration_service import generate_story_for_analysis, get_existing_story_for_analysis
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Stories"])
logger = logging.getLogger(__name__)


@router.post("/videos/{video_id}/story", response_model=NarrativeGenerationResponse)
def create_story(video_id: str, request: StoryRequest) -> dict:
    # Reuse the upload lookup to validate the UUID and distinguish unknown videos.
    get_uploaded_video_path(video_id)
    logger.info("[STORY_GENERATE_REQUEST] analysis_id=%s", video_id)
    return generate_story_for_analysis(video_id, language=request.language)


@router.get("/videos/{video_id}/story", response_model=NarrativeGenerationResponse)
def get_story(video_id: str, language: str = "en") -> dict:
    """Read an existing generated Story without invoking Gemini."""
    get_uploaded_video_path(video_id)
    logger.info("[STORY_GET] analysis_id=%s language=%s", video_id, language)
    return get_existing_story_for_analysis(video_id, language=language)
