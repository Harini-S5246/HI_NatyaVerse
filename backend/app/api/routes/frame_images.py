"""Serve extracted frame images with video_id isolation and path traversal protection."""
import logging
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Frame Images"])


def validate_frame_path(video_id: str, frame_filename: str) -> Path:
    """
    Validate and construct the frame file path with security checks.
    
    Protects against path traversal by:
    1. Checking video_id contains only alphanumeric and hyphens
    2. Checking frame_filename contains only alphanumeric, dots, hyphens, underscores
    3. Resolving the path and ensuring it stays within the video_id directory
    
    Args:
        video_id: The video identifier
        frame_filename: The frame filename
        
    Returns:
        Path to the frame file if valid
        
    Raises:
        AppError: If validation fails or file not found
    """
    # Validate video_id format
    if not video_id or not video_id.replace("-", "").isalnum():
        raise AppError("Invalid video_id.", 400, "INVALID_VIDEO_ID")
    
    # Validate frame_filename format (allow . for extension, - and _ for naming)
    if not frame_filename:
        raise AppError("Frame filename is required.", 400, "INVALID_FRAME_FILENAME")
    
    # Only allow safe characters in filename
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    if not all(c in allowed_chars for c in frame_filename):
        raise AppError("Frame filename contains invalid characters.", 400, "INVALID_FRAME_FILENAME")
    
    # Construct the path
    video_frames_dir = settings.frame_output_dir / video_id
    frame_path = video_frames_dir / frame_filename
    
    # Resolve to absolute path and verify it's within the video_id directory
    try:
        resolved = frame_path.resolve()
        resolved_dir = video_frames_dir.resolve()
        
        # Ensure the resolved path is within the video directory (path traversal protection)
        if not str(resolved).startswith(str(resolved_dir)):
            raise AppError("Access denied: path traversal attempt.", 403, "PATH_TRAVERSAL_BLOCKED")
        
        # Check that the file exists
        if not resolved.is_file():
            raise AppError("Frame file not found.", 404, "FRAME_NOT_FOUND")
        
        return resolved
    except (OSError, ValueError) as exc:
        logger.warning("Frame path validation failed: video_id=%s frame=%s error=%s", video_id, frame_filename, exc)
        raise AppError("Invalid frame path.", 400, "INVALID_FRAME_PATH") from exc


@router.get("/videos/{video_id}/frames/{frame_filename}")
async def get_frame_image(video_id: str, frame_filename: str) -> FileResponse:
    """
    Serve an extracted frame image.
    
    Security:
    - Only serves frames from the requested video_id directory
    - Prevents path traversal attacks
    - Validates video_id and filename format
    
    Args:
        video_id: The video identifier
        frame_filename: The frame filename (e.g., "frame_000000.jpg")
        
    Returns:
        FileResponse with the frame image
        
    Raises:
        404: If the frame does not exist
        400: If video_id or filename format is invalid
        403: If path traversal is attempted
    """
    frame_path = validate_frame_path(video_id, frame_filename)
    
    logger.debug("Serving frame image: video_id=%s frame=%s path=%s", video_id, frame_filename, frame_path)
    
    return FileResponse(
        path=frame_path,
        media_type="image/jpeg",
        filename=frame_filename,
    )
