from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.services.frame_service import extract_sampled_frames
from app.services.upload_service import get_uploaded_video_path


router = APIRouter(prefix="/api", tags=["Frames"])


class FrameExtractionRequest(BaseModel):
    sampling_interval: float = Field(
        default=1.0,
        gt=0,
        le=60,
        description="Seconds between sampled frames; must be greater than 0 and no more than 60.",
    )


@router.post("/videos/{video_id}/frames")
def extract_video_frames(video_id: str, request: FrameExtractionRequest) -> dict:
    video_path = get_uploaded_video_path(video_id)
    return extract_sampled_frames(video_path, video_id, request.sampling_interval)
