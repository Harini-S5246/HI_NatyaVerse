import logging
from fastapi import APIRouter, File, Form, UploadFile
from app.core.errors import AppError
from app.models.model_manager import model_manager
from app.services.frame_service import iter_sampled_frames
from app.services.multimodal_service import build_result
from app.services.result_service import save_result
from app.services.upload_service import save_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Analysis"])

@router.post("/analyze")
async def analyze_video(video: UploadFile = File(...), sampling_interval: float = Form(1.0), language: str | None = Form(None)) -> dict:
    if sampling_interval <= 0:
        raise AppError("sampling_interval must be greater than zero.", 400, "INVALID_SAMPLING_INTERVAL")
    missing = model_manager.missing_models()
    if missing:
        raise AppError("Required trained model files are not configured in the local environment.", 503, "MODEL_UNAVAILABLE", {"status": "model_unavailable", "missing_models": missing})
    video_path, metadata = await save_upload(video)
    analysis_id = video_path.stem
    logger.info("Starting analysis: id=%s language=%s", analysis_id, language)
    timeline = []
    try:
        adapters = {name: model_manager.get(name) for name in ("mudra", "bhava", "pose")}
        for timestamp, frame in iter_sampled_frames(video_path, sampling_interval):
            timeline.append({"timestamp_sec": timestamp, **{name: adapters[name].predict(frame) for name in adapters}})
        result = build_result(analysis_id, metadata, timeline)
        save_result(result)
        logger.info("Result saved: id=%s frames=%s", analysis_id, len(timeline))
        return {"analysis_id": analysis_id, "status": "completed"}
    except Exception as exc:
        logger.exception("Analysis failed: id=%s", analysis_id)
        raise AppError("Inference failed; no result was fabricated.", 500, "INFERENCE_FAILED") from exc

@router.get("/analysis/{analysis_id}/status")
def analysis_status(analysis_id: str) -> dict:
    from app.services.result_service import get_result
    try:
        result = get_result(analysis_id)
        return {"analysis_id": analysis_id, "status": result.get("status", "completed"), "stage": "completed", "progress": 100}
    except AppError as exc:
        if exc.status_code == 404:
            return {"analysis_id": analysis_id, "status": "failed", "stage": "unavailable", "message": "Analysis result is not available."}
        raise

@router.get("/analysis/{analysis_id}")
@router.get("/analysis/{analysis_id}/result")
def analysis_result(analysis_id: str) -> dict:
    from app.services.result_service import get_result
    return get_result(analysis_id)
