"""API routes for isolated Story-to-Dance planning."""
import hashlib
import json
import logging
import mimetypes
from threading import Lock
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.api.schemas.story_to_dance import (
    StoryToDanceRecord,
    StoryToDanceStoryRequest,
    StoryToDanceWorkflowRequest,
)
from app.api.schemas.dance_generation import (
    DanceGenerationResult,
    StoryToDanceWorkflowResponse,
)
from app.core.errors import AppError
from app.services import story_dance_reference_service, story_to_dance_service
from app.services.dance_generation_service import (
    generate_dance_performance,
    get_dance_performance_video,
)
from app.services.story_to_dance_service import (
    create_story,
    generate_dance_plan,
    get_story,
)
from app.services.story_dance_reference_service import (
    SceneVisualReferences,
    SceneVisualReferencesRequest,
    get_scene_visual_references,
)
from app.utils.json_utils import load_json, save_json

router = APIRouter(prefix="/api/story-to-dance/stories", tags=["Story to Dance"])
logger = logging.getLogger(__name__)
_workflow_locks: dict[str, Lock] = {}
_workflow_locks_guard = Lock()


def _workflow_lock(request_id: str) -> Lock:
    with _workflow_locks_guard:
        return _workflow_locks.setdefault(request_id, Lock())


def _workflow_path(request_id: str) -> Path:
    return (
        story_to_dance_service.settings.results_dir
        / "story_to_dance"
        / "workflows"
        / f"{request_id}.json"
    )


def _persist_workflow(path: Path, state: dict) -> None:
    try:
        save_json(path, state)
    except OSError as exc:
        logger.exception("Story-to-Dance workflow state could not be saved.")
        raise AppError(
            "The Story-to-Dance workflow state could not be saved.",
            500,
            "STORY_TO_DANCE_WORKFLOW_STORE_UNAVAILABLE",
        ) from exc


def _parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    try:
        raw = range_header.split("=", 1)[1].strip()
        if "," in raw:
            raw = raw.split(",", 1)[0].strip()
        start_text, _, end_text = raw.partition("-")
        start = int(start_text) if start_text else 0
        end = int(end_text) if end_text else file_size - 1
        if start >= file_size:
            return None
        if end >= file_size:
            end = file_size - 1
        return start, end
    except ValueError:
        return None


@router.post("", response_model=StoryToDanceRecord, status_code=201)
def create_story_record(request: StoryToDanceStoryRequest) -> dict:
    return create_story(
        request.story_text,
        language=request.language,
        title=request.title,
    )


@router.post(
    "/visual-references",
    response_model=list[SceneVisualReferences],
)
def read_story_dance_visual_references(
    request: SceneVisualReferencesRequest,
) -> list[SceneVisualReferences]:
    scene_ids = [scene.scene_id for scene in request.scenes]
    try:
        return get_scene_visual_references(request)
    except AppError:
        raise
    except Exception as exc:
        logger.exception(
            "Story-to-Dance visual reference lookup failed: scene_ids=%s",
            scene_ids,
        )
        raise AppError(
            "Reference lookup failed because the server encountered an internal error. "
            "Check backend logs using the scene IDs.",
            500,
            "STORY_DANCE_REFERENCE_LOOKUP_FAILED",
            {"scene_ids": scene_ids},
        ) from exc


@router.get("/reference-assets/{asset_id}")
def read_story_dance_reference_asset(asset_id: str) -> FileResponse:
    asset_path = story_dance_reference_service.get_dataset_reference_asset_path(asset_id)
    return FileResponse(
        path=asset_path,
        media_type=mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream",
        filename=asset_path.name,
    )


@router.post("/workflow", response_model=StoryToDanceWorkflowResponse)
def create_story_to_dance_workflow(
    request: StoryToDanceWorkflowRequest,
) -> dict:
    request_id = str(request.request_id)
    request_payload = request.model_dump(mode="json", exclude={"request_id"})
    request_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    path = _workflow_path(request_id)

    with _workflow_lock(request_id):
        state = None
        if path.is_file():
            try:
                state = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                logger.exception(
                    "Story-to-Dance workflow state could not be read: request_id=%s",
                    request_id,
                )
                raise AppError(
                    "The saved Story-to-Dance workflow could not be read.",
                    500,
                    "STORY_TO_DANCE_WORKFLOW_STORE_UNAVAILABLE",
                ) from exc
            if not isinstance(state, dict) or state.get("request_hash") != request_hash:
                raise AppError(
                    "This request ID was already used with different story details.",
                    409,
                    "STORY_TO_DANCE_REQUEST_ID_CONFLICT",
                )
            if isinstance(state.get("response"), dict):
                return state["response"]

        if not isinstance(state, dict) or not state.get("story_id"):
            story = create_story(
                request.story_text,
                language=request.language,
                title=request.title,
            )
            state = {
                "request_hash": request_hash,
                "story_id": story["story_id"],
                "status": "story_created",
            }
            _persist_workflow(path, state)
        else:
            story = get_story(state["story_id"])

        if not isinstance(story.get("dance_plan"), dict):
            story = generate_dance_plan(story["story_id"])
            state["status"] = "plan_ready"
            _persist_workflow(path, state)

        dance_plan = story.get("dance_plan")
        if not isinstance(dance_plan, dict) or not dance_plan.get("dance_plan_id"):
            raise AppError(
                "The story planner did not produce a usable dance plan.",
                502,
                "DANCE_PLAN_UNAVAILABLE",
            )
        generation = generate_dance_performance(
            story["story_id"],
            dance_plan["dance_plan_id"],
        )
        response = {
            "story": story,
            "generation": generation,
        }
        state.update({"status": "completed", "response": response})
        _persist_workflow(path, state)
        return response


@router.get("/workflow/{request_id}", response_model=StoryToDanceWorkflowResponse)
def read_story_to_dance_workflow(request_id: str) -> dict:
    try:
        normalized_request_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AppError("Workflow request ID is invalid.", 400, "INVALID_WORKFLOW_REQUEST_ID") from exc
    if normalized_request_id != request_id:
        raise AppError("Workflow request ID is invalid.", 400, "INVALID_WORKFLOW_REQUEST_ID")

    path = _workflow_path(normalized_request_id)
    if not path.is_file():
        raise AppError("Story-to-Dance workflow was not found.", 404, "WORKFLOW_NOT_FOUND")
    try:
        state = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception(
            "Story-to-Dance workflow state could not be read: request_id=%s",
            normalized_request_id,
        )
        raise AppError(
            "The saved Story-to-Dance workflow could not be read.",
            500,
            "STORY_TO_DANCE_WORKFLOW_STORE_UNAVAILABLE",
        ) from exc
    if not isinstance(state, dict) or not isinstance(state.get("response"), dict):
        raise AppError(
            "The Story-to-Dance workflow has not completed yet.",
            409,
            "STORY_TO_DANCE_WORKFLOW_INCOMPLETE",
        )
    return state["response"]


@router.get("/{story_id}", response_model=StoryToDanceRecord)
def read_story_record(story_id: str) -> dict:
    return get_story(story_id)


@router.post("/{story_id}/plan", response_model=StoryToDanceRecord)
def create_dance_plan(story_id: str) -> dict:
    return generate_dance_plan(story_id)


@router.post(
    "/{story_id}/plans/{dance_plan_id}/performance",
    response_model=DanceGenerationResult,
)
def create_dance_performance(story_id: str, dance_plan_id: str) -> dict:
    return generate_dance_performance(story_id, dance_plan_id)


@router.get(
    "/{story_id}/plans/{dance_plan_id}/choreographies/"
    "{choreography_id}/generations/{generation_id}/video",
    response_class=FileResponse,
)
def read_dance_performance_video(
    story_id: str,
    dance_plan_id: str,
    choreography_id: str,
    generation_id: str,
    request: Request,
):
    video_path: Path = get_dance_performance_video(
        story_id,
        dance_plan_id,
        choreography_id,
        generation_id,
    )
    file_size = video_path.stat().st_size
    range_header = request.headers.get("Range")
    range_boundaries = _parse_range_header(range_header, file_size)
    if range_boundaries is not None:
        start, end = range_boundaries
        with video_path.open("rb") as handle:
            handle.seek(start)
            payload = handle.read(end - start + 1)
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(len(payload)),
            "Accept-Ranges": "bytes",
        }
        return StreamingResponse(
            iter([payload]),
            status_code=206,
            media_type="video/mp4",
            headers=headers,
        )
    response = FileResponse(
        video_path,
        media_type="video/mp4",
        filename="dance-performance.mp4",
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response
