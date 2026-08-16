from fastapi import APIRouter

from app.api.schemas.fusion import FusionResponse
from app.services.fusion_service import fuse_video
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Fusion"])


@router.post("/videos/{video_id}/fusion", response_model=FusionResponse)
def fuse_video_route(video_id: str) -> dict:
    # Reuse the upload lookup to validate the UUID and distinguish unknown videos.
    get_uploaded_video_path(video_id)
    return fuse_video(video_id)