from __future__ import annotations
import logging
from pathlib import Path
from app.core.errors import AppError
logger = logging.getLogger(__name__)
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

def validate_video_path(path: Path) -> dict:
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AppError("Unsupported video file type.", 400, "UNSUPPORTED_FILE_TYPE")
    try:
        import cv2
    except ImportError as exc:
        raise AppError("Video validation requires opencv-python to be installed.", 503, "VIDEO_BACKEND_UNAVAILABLE") from exc
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AppError("The uploaded file is not a readable video.", 400, "INVALID_VIDEO")
    fps, frame_count = float(capture.get(cv2.CAP_PROP_FPS) or 0), int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    capture.release()
    if fps <= 0 or frame_count <= 0:
        raise AppError("The uploaded video has no readable frames.", 400, "INVALID_VIDEO")
    metadata = {"fps": fps, "frame_count": frame_count, "width": width, "height": height, "duration_seconds": frame_count / fps}
    logger.info("Video metadata: %s", metadata)
    return metadata
