from fastapi import APIRouter

from app.api.schemas.story import StoryRequest, StoryResponse
from app.services.story_service import generate_story
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Stories"])


@router.post("/videos/{video_id}/story", response_model=StoryResponse)
def create_story(video_id: str, request: StoryRequest) -> dict:
    # Reuse the upload lookup to validate the UUID and distinguish unknown videos.
    get_uploaded_video_path(video_id)
    return generate_story(video_id, request.language)