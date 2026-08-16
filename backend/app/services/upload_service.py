from __future__ import annotations
import logging
import uuid
from pathlib import Path
from fastapi import UploadFile
from app.config import settings
from app.core.errors import AppError
from app.services.video_service import ALLOWED_EXTENSIONS, validate_video_path

logger = logging.getLogger(__name__)


def get_uploaded_video_path(video_id: str) -> Path:
    """Find a video saved by ``save_upload`` without accepting arbitrary paths."""
    try:
        parsed_id = uuid.UUID(video_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise AppError("Uploaded video was not found.", 404, "VIDEO_NOT_FOUND") from exc

    # Upload IDs are generated with str(uuid.uuid4()), so require that exact form.
    if str(parsed_id) != video_id:
        raise AppError("Uploaded video was not found.", 404, "VIDEO_NOT_FOUND")

    upload_dir = settings.upload_dir.resolve()
    for extension in ALLOWED_EXTENSIONS:
        candidate = (upload_dir / f"{video_id}{extension}").resolve()
        if candidate.parent == upload_dir and candidate.is_file():
            return candidate

    raise AppError("Uploaded video was not found.", 404, "VIDEO_NOT_FOUND")


async def save_upload(video: UploadFile) -> tuple[Path, dict]:
    if not video.filename:
        raise AppError("No video file provided.", 400, "MISSING_VIDEO")
    suffix = Path(video.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AppError(f"Unsupported video format: {suffix or 'unknown'}.", 400, "UNSUPPORTED_FILE_TYPE")
    destination = settings.upload_dir / f"{uuid.uuid4()}{suffix}"
    size = 0
    try:
        with destination.open("wb") as stream:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    stream.close()
                    destination.unlink(missing_ok=True)
                    raise AppError("Video exceeds the configured upload-size limit.", 413, "FILE_TOO_LARGE")
                stream.write(chunk)
        metadata = validate_video_path(destination)
        metadata["original_filename"] = Path(video.filename).name
        metadata["file_size_bytes"] = size
        logger.info("Upload received: id=%s size=%s", destination.stem, size)
        return destination, metadata
    except AppError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Upload save failed")
        raise AppError("Failed to save the uploaded video.", 500, "UPLOAD_FAILED") from exc
    finally:
        await video.close()
