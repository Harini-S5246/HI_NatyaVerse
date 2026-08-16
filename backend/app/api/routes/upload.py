from fastapi import APIRouter, File, UploadFile
from app.core.errors import AppError
from app.services.upload_service import save_upload

router = APIRouter(prefix="/api", tags=["Upload"])

@router.post("/upload")
async def upload_video(video: UploadFile = File(...)) -> dict:
    path, metadata = await save_upload(video)
    return {"status": "uploaded", "video_id": path.stem, "filename": video.filename, "metadata": metadata}
