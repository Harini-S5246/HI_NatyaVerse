from collections.abc import Iterator
from pathlib import Path
from app.config import settings
from app.core.errors import AppError
from app.services.video_service import validate_video_path
from app.utils.json_utils import save_json


def iter_sampled_frames(video_path: Path, sampling_interval: float) -> Iterator[tuple[float, object]]:
    """Yield BGR frames sequentially; never load an entire video into memory."""
    import cv2
    capture = cv2.VideoCapture(str(video_path))
    try:
        fps, index = float(capture.get(cv2.CAP_PROP_FPS)), 0
        step = max(1, round(fps * sampling_interval))
        while True:
            ok, frame = capture.read()
            if not ok: break
            if index % step == 0: yield index / fps, frame
            index += 1
    finally: capture.release()


def extract_sampled_frames(video_path: Path, video_id: str, sampling_interval: float) -> dict:
    """Persist sampled JPEG frames and a compact manifest for one uploaded video."""
    validate_video_path(video_path)
    output_dir = settings.frame_output_dir / video_id
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, int | float | str]] = []

    try:
        import cv2

        for frame_number, (timestamp, frame) in enumerate(iter_sampled_frames(video_path, sampling_interval)):
            filename = f"frame_{frame_number:06d}.jpg"
            if not cv2.imwrite(str(output_dir / filename), frame, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                raise AppError("Failed to save an extracted frame.", 500, "FRAME_EXTRACTION_FAILED")
            frames.append({"frame_number": frame_number, "timestamp": round(timestamp, 3), "filename": filename})
    except AppError:
        raise
    except Exception as exc:
        raise AppError("Frame extraction failed.", 500, "FRAME_EXTRACTION_FAILED") from exc

    if not frames:
        raise AppError("No readable frames could be extracted from this video.", 400, "INVALID_VIDEO")

    manifest = {
        "video_id": video_id,
        "sampling_interval": sampling_interval,
        "frame_count": len(frames),
        "frames": frames,
    }
    save_json(output_dir / "manifest.json", manifest)
    return manifest
