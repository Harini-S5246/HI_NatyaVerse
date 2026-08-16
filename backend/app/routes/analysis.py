from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid
import shutil

router = APIRouter(
    prefix="/api",
    tags=["Analysis"]
)

# Directory where uploaded performance videos are stored
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Supported video formats
ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}


@router.post("/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """
    Upload a Bharatanatyam performance video.

    This endpoint currently handles only the upload/storage stage.
    The real Mudra + Bhava + Pose + multimodal AI pipeline
    will be connected after the upload flow is verified.
    """

    # Check that a file was provided
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No video file provided."
        )

    # Get file extension
    extension = Path(file.filename).suffix.lower()

    # Validate video format
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported video format: {extension}. "
                f"Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        )

    # Generate unique analysis ID
    analysis_id = str(uuid.uuid4())

    # Create unique filename
    saved_filename = f"{analysis_id}{extension}"
    saved_path = UPLOAD_DIR / saved_filename

    try:
        # Save uploaded video
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded video: {str(exc)}"
        )

    finally:
        await file.close()

    return {
        "success": True,
        "analysis_id": analysis_id,
        "filename": file.filename,
        "saved_file": str(saved_path),
        "status": "uploaded",
        "message": (
            "Video uploaded successfully. "
            "Analysis pipeline is ready to start."
        )
    }