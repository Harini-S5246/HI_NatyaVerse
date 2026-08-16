from fastapi import APIRouter

from app.api.schemas.mudra import MudraClassificationResponse
from app.services.mudra_service import classify_video_frames
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Mudras"])


@router.post("/videos/{video_id}/mudras", response_model=MudraClassificationResponse)
def classify_mudras(video_id: str) -> dict:
    # Reuse the upload lookup to validate the UUID and distinguish unknown videos.
    get_uploaded_video_path(video_id)
    return classify_video_frames(video_id)
