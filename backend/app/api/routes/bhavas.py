from fastapi import APIRouter

from app.api.schemas.bhava import BhavaClassificationResponse
from app.services.bhava_service import classify_video_bhava
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Bhavas"])


@router.post("/videos/{video_id}/bhavas", response_model=BhavaClassificationResponse)
def classify_bhavas(video_id: str) -> dict:
    # Reuse the upload lookup to validate the UUID and distinguish unknown videos.
    get_uploaded_video_path(video_id)
    return classify_video_bhava(video_id)