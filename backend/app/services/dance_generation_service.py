"""Strict adapter boundary for optional Story-to-Dance performance generation."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.api.schemas.dance_generation import (
    DanceGenerationResult,
    DanceGenerationSceneTiming,
    DanceGenerationSceneStatus,
    DanceGeneratorOutput,
    DanceMovementCoverage,
    StoryDanceGenerationRequest,
)
from app.config import settings
from app.core.errors import AppError
from app.services.story_dance_avatar_service import RiggedBharatanatyamDancerGenerator
from app.services.story_to_dance_service import get_story
from app.services.video_service import validate_video_path
from app.utils.json_utils import load_json, save_json

logger = logging.getLogger(__name__)
_NO_GENERATOR_REASON = (
    "Blender is not available in this environment. The project-built 3D dancer renderer requires Blender to produce a video."
)
_OUTPUT_LIMITATIONS = [
    "This is an AI-assisted, project-built 3D animation, not photorealistic AI video.",
    "The visualization is Bharatanatyam-inspired and has not been validated by a Bharatanatyam expert.",
]


class DanceGenerationError(Exception):
    """Expected generator failure with a user-safe, actionable reason."""

    def __init__(
        self,
        message: str,
        error_code: str = "INVALID_GENERATION_OUTPUT",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class DanceGenerator(Protocol):
    """Implementations must provide documented model metadata and a playable MP4."""

    def generate(self, request: StoryDanceGenerationRequest) -> DanceGeneratorOutput:
        """Generate temporal poses and an MP4 for the validated request."""


def get_dance_generator() -> DanceGenerator | None:
    """Return the configured rigged 3D dancer generator when a usable asset exists."""

    if not RiggedBharatanatyamDancerGenerator.is_available():
        return None
    return RiggedBharatanatyamDancerGenerator()


def _generation_directory(results_dir: Path, story_id: str) -> Path:
    return results_dir / "story_to_dance" / "generations" / story_id


def _generation_path(
    results_dir: Path,
    story_id: str,
    generation_id: str,
) -> Path:
    return (
        _generation_directory(results_dir, story_id)
        / generation_id
    )


def _build_request(
    story_id: str,
    dance_plan_id: str,
    plan: dict,
    generation_id: str,
    output_directory: Path,
) -> StoryDanceGenerationRequest:
    if (
        plan.get("story_id") != story_id
        or plan.get("dance_plan_id") != dance_plan_id
        or not isinstance(plan.get("choreography_id"), str)
    ):
        raise AppError("The saved choreography identity is invalid.", 500, "CHOREOGRAPHY_ID_MISMATCH")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise AppError("The saved choreography has no scenes.", 409, "CHOREOGRAPHY_UNAVAILABLE")

    request_scenes = []
    scene_ids: set[str] = set()
    for expected_order, scene in enumerate(scenes, start=1):
        if (
            not isinstance(scene, dict)
            or scene.get("scene_order") != expected_order
            or not isinstance(scene.get("scene_id"), str)
            or scene["scene_id"] in scene_ids
        ):
            raise AppError(
                "The saved choreography scene identity or order is invalid.",
                500,
                "INVALID_CHOREOGRAPHY_ORDER",
            )
        scene_ids.add(scene["scene_id"])
        movement_intent = scene.get("movement_intent")
        if not isinstance(movement_intent, dict):
            raise AppError("A scene has no movement-intent contract.", 500, "INVALID_CHOREOGRAPHY")
        request_scenes.append({
            "scene_id": scene["scene_id"],
            "scene_order": scene["scene_order"],
            "source_text": scene["source_text"],
            "action": scene["action"],
            "objects": scene["objects"],
            "location": scene["location"],
            "movement_intent": movement_intent,
            "mudra": scene["mudra"],
            "bhava": scene["bhava"],
            "movement_concept": scene["bharatanatyam_concept"],
            "visualization_sequence": scene.get("visualization_sequence", []),
            "candidate_adavu": scene["candidate_adavu"],
            "mapping_status": scene["mapping_status"],
            "source_provenance": scene["source_provenance"],
            "generator_label": scene["generator_label"],
            "duration_seconds": scene["duration_estimate_seconds"],
        })
    return StoryDanceGenerationRequest(
        generation_id=generation_id,
        story_id=story_id,
        dance_plan_id=dance_plan_id,
        choreography_id=plan["choreography_id"],
        output_directory=output_directory,
        scenes=request_scenes,
    )


def _unavailable_result(
    request: StoryDanceGenerationRequest,
    generation_id: str,
    reason: str,
    *,
    error_code: str = "MODEL_UNAVAILABLE",
) -> DanceGenerationResult:
    return DanceGenerationResult(
        generation_id=generation_id,
        story_id=request.story_id,
        dance_plan_id=request.dance_plan_id,
        choreography_id=request.choreography_id,
        status="unavailable",
        scenes=[
            DanceGenerationSceneStatus(
                scene_id=scene.scene_id,
                scene_order=scene.scene_order,
                status=(
                    "review_required"
                    if scene.mapping_status == "review_required"
                    else "unavailable"
                ),
                generator_label=scene.generator_label,
                mapping_status=scene.mapping_status,
                movement_concepts=[
                    concept.concept
                    for concept in scene.movement_concept
                    if concept.mapping_status == "supported_concept"
                ],
                candidate_adavu=None,
                movement_sequence=[],
                mudra=[
                    item.mudra
                    for item in scene.mudra
                    if item.status == "mapped" and item.mudra
                ],
                action=scene.action,
                target=None,
                direction=scene.movement_intent.direction,
                transition="No renderer output available.",
                expressive_state="neutral",
                source_provenance=scene.source_provenance,
                reason=(
                    "Movement mapping for this scene remains review-required."
                    if not any(
                        concept.mapping_status == "supported_concept"
                        for concept in scene.movement_concept
                    )
                    else reason
                ),
            )
            for scene in request.scenes
        ],
        movement_coverage=DanceMovementCoverage(
            generated_scenes=0,
            total_scenes=len(request.scenes),
            source_supported_scenes=sum(
                any(
                    concept.mapping_status == "supported_concept"
                    for concept in scene.movement_concept
                )
                for scene in request.scenes
            ),
        ),
        provenance=[],
        reason=reason,
        error_code=error_code,
        limitations=list(_OUTPUT_LIMITATIONS),
    )


def _validate_generator_output(
    output: DanceGeneratorOutput,
    request: StoryDanceGenerationRequest,
) -> dict[str, int]:
    expected = [(scene.scene_id, scene.scene_order) for scene in request.scenes]
    actual = [(scene.scene_id, scene.scene_order) for scene in output.scenes]
    if actual != expected:
        raise DanceGenerationError("The generator returned scenes with mismatched IDs or order.")
    if (
        output.generation_id != request.generation_id
        or output.story_id != request.story_id
        or output.dance_plan_id != request.dance_plan_id
        or output.choreography_id != request.choreography_id
    ):
        raise DanceGenerationError("The generator output belongs to a different generation or plan.")
    previous_end_frame = -1
    for scene_request, scene_result in zip(request.scenes, output.scenes):
        if scene_result.status == "generated":
            if scene_result.generator_label is not None:
                raise DanceGenerationError(
                    f"Scene {scene_request.scene_order} claimed a validated generator label."
                )
            if (
                scene_result.start_frame_index is None
                or scene_result.end_frame_index is None
                or scene_result.start_frame_index > scene_result.end_frame_index
                or scene_result.end_frame_index >= len(output.pose_sequence)
                or scene_result.start_frame_index <= previous_end_frame
            ):
                raise DanceGenerationError(
                    f"Scene {scene_request.scene_order} has an invalid temporal frame range."
                )
            expected_concepts = [
                concept.concept
                for concept in scene_request.movement_concept
                if concept.mapping_status == "supported_concept"
            ]
            expected_mudras = [
                item.mudra
                for item in scene_request.mudra
                if item.status == "mapped" and item.mudra
            ]
            expected_action = " + ".join(
                action.action for action in scene_request.movement_intent.actions
            ) or scene_request.movement_intent.action
            expected_direction = " → ".join(
                action.direction or "—"
                for action in scene_request.movement_intent.actions
            ) or scene_request.movement_intent.direction
            expected_provenance = [
                provenance.model_dump(mode="json")
                for provenance in scene_request.source_provenance
            ]
            if (
                scene_result.action != expected_action
                or scene_result.mudra != expected_mudras
                or scene_result.direction != expected_direction
            ):
                raise DanceGenerationError(
                    f"Scene {scene_request.scene_order} result does not preserve its action, Mudra, or direction."
                )
            scene_frames = output.pose_sequence[
                scene_result.start_frame_index : scene_result.end_frame_index + 1
            ]
            if any(
                frame.pose_data.get("scene_id") != scene_request.scene_id
                or frame.pose_data.get("scene_order") != scene_request.scene_order
                or frame.pose_data.get("movement_concepts") != expected_concepts
                or frame.pose_data.get("mapping_status") != scene_request.mapping_status
                or frame.pose_data.get("candidate_adavu") is not None
                or frame.pose_data.get("movement_intent")
                != scene_request.movement_intent.model_dump(mode="json")
                or frame.pose_data.get("movement_sequence")
                != scene_result.movement_sequence
                or frame.pose_data.get("mudra") != scene_result.mudra
                or frame.pose_data.get("target") != scene_result.target
                or frame.pose_data.get("direction") != scene_result.direction
                or frame.pose_data.get("transition") != scene_result.transition
                or frame.pose_data.get("expressive_state") != scene_result.expressive_state
                or frame.pose_data.get("source_provenance") != expected_provenance
                for frame in scene_frames
            ):
                raise DanceGenerationError(
                    f"Scene {scene_request.scene_order} pose frames do not preserve its scene data and movement mapping."
                )
            previous_end_frame = scene_result.end_frame_index
        elif scene_result.start_frame_index is not None or scene_result.end_frame_index is not None:
            raise DanceGenerationError(
                f"Unavailable scene {scene_request.scene_order} cannot claim generated frame indexes."
            )
    if not all(scene.status == "generated" for scene in output.scenes):
        raise DanceGenerationError(
            "The avatar renderer must preserve every ordered scene in the visualization."
        )
    frame_indexes = [frame.frame_index for frame in output.pose_sequence]
    if frame_indexes != list(range(len(frame_indexes))):
        raise DanceGenerationError("The generator returned non-contiguous frame indexes.")
    if any(not frame.pose_data for frame in output.pose_sequence):
        raise DanceGenerationError("The generator returned an empty pose frame.")
    timestamps = [frame.timestamp_seconds for frame in output.pose_sequence]
    if any(later <= earlier for earlier, later in zip(timestamps, timestamps[1:])):
        raise DanceGenerationError("The generator returned unordered frame timestamps.")
    if any(
        abs(timestamp - (index / output.fps)) > max(0.02, 1 / output.fps)
        for index, timestamp in enumerate(timestamps)
    ):
        raise DanceGenerationError("The pose timestamps do not match the reported FPS.")
    if timestamps[-1] >= output.duration_seconds:
        raise DanceGenerationError("The pose sequence extends beyond the reported duration.")
    if (
        output.scenes[0].start_frame_index != 0
        or output.scenes[-1].end_frame_index != len(output.pose_sequence) - 1
        or any(
            current.start_frame_index != previous.end_frame_index + 1
            for previous, current in zip(output.scenes, output.scenes[1:])
        )
    ):
        raise DanceGenerationError(
            "Scene frame ranges must preserve the complete, contiguous ordered timeline."
        )
    try:
        output_path = output.video_path.resolve(strict=True)
        output_directory = request.output_directory.resolve(strict=True)
    except OSError as exc:
        raise DanceGenerationError("The generator did not produce an output file.") from exc
    if (
        output_path.parent != output_directory
        or output_path.name != "dance-performance.mp4"
        or output_path.suffix.casefold() != ".mp4"
        or not output_path.is_file()
        or output_path.stat().st_size == 0
    ):
        raise DanceGenerationError(
            "The generator did not produce a non-empty MP4 in this generation's output directory.",
            "VIDEO_RENDER_FAILED",
        )
    try:
        video_metadata = validate_video_path(output.video_path)
        import cv2

        capture = cv2.VideoCapture(str(output.video_path))
        try:
            codec = int(capture.get(cv2.CAP_PROP_FOURCC)).to_bytes(
                4,
                "little",
            ).decode("ascii", errors="replace").strip("\x00").casefold()
            first_readable, _ = capture.read()
            if video_metadata["frame_count"] > 0:
                capture.set(
                    cv2.CAP_PROP_POS_FRAMES,
                    video_metadata["frame_count"] - 1,
                )
            last_readable, _ = capture.read()
        finally:
            capture.release()
    except (AppError, OSError, ImportError) as exc:
        raise DanceGenerationError(
            "The generated MP4 could not be decoded or validated.",
            "VIDEO_VALIDATION_FAILED",
        ) from exc
    if codec not in {"h264", "avc1"}:
        raise DanceGenerationError(
            f"The generated MP4 uses non-browser-targeted codec {codec!r}; H.264 is required.",
            "VIDEO_VALIDATION_FAILED",
        )
    if not first_readable or not last_readable:
        raise DanceGenerationError(
            "The generated MP4 first or final frame cannot be decoded.",
            "VIDEO_VALIDATION_FAILED",
        )
    if abs(video_metadata["fps"] - output.fps) > 0.1:
        raise DanceGenerationError(
            "The reported FPS does not match the generated MP4.",
            "VIDEO_VALIDATION_FAILED",
        )
    if video_metadata["frame_count"] != len(output.pose_sequence):
        raise DanceGenerationError(
            "The MP4 frame count does not match the pose sequence.",
            "VIDEO_VALIDATION_FAILED",
        )
    if video_metadata["width"] <= 0 or video_metadata["height"] <= 0:
        raise DanceGenerationError(
            "The generated MP4 has invalid frame dimensions.",
            "VIDEO_VALIDATION_FAILED",
        )
    if (
        output.video_width is not None
        and output.video_width != video_metadata["width"]
    ) or (
        output.video_height is not None
        and output.video_height != video_metadata["height"]
    ):
        raise DanceGenerationError(
            "The declared video dimensions do not match the generated MP4.",
            "VIDEO_VALIDATION_FAILED",
        )
    duration_tolerance = max(0.25, 1 / output.fps)
    if abs(video_metadata["duration_seconds"] - output.duration_seconds) > duration_tolerance:
        raise DanceGenerationError(
            "The reported duration does not match the generated MP4.",
            "VIDEO_VALIDATION_FAILED",
        )
    return {
        "width": video_metadata["width"],
        "height": video_metadata["height"],
    }


def _persist(
    results_dir: Path,
    result: DanceGenerationResult,
) -> None:
    generation_directory = _generation_path(
        results_dir,
        result.story_id,
        result.generation_id,
    )
    try:
        generation_directory.mkdir(parents=True, exist_ok=True)
        save_json(generation_directory / "result.json", result.model_dump(mode="json"))
    except OSError as exc:
        logger.exception(
            "Story-to-Dance generation result could not be saved: story_id=%s generation_id=%s",
            result.story_id,
            result.generation_id,
        )
        raise AppError(
            "The dance generation result could not be saved.",
            500,
            "DANCE_GENERATION_STORE_UNAVAILABLE",
        ) from exc


def generate_dance_performance(story_id: str, dance_plan_id: str) -> dict:
    story = get_story(story_id)
    plan = story.get("dance_plan")
    if not isinstance(plan, dict):
        raise AppError("Generate a Story-to-Dance plan first.", 409, "DANCE_PLAN_REQUIRED")
    if plan.get("dance_plan_id") != dance_plan_id:
        raise AppError(
            "The requested dance plan is no longer current.",
            409,
            "STALE_GENERATION",
        )
    generation_id = str(uuid.uuid4())
    generation_directory = _generation_path(
        settings.results_dir,
        story_id,
        generation_id,
    )
    request = _build_request(
        story_id,
        dance_plan_id,
        plan,
        generation_id,
        generation_directory,
    )
    generator = get_dance_generator()

    if generator is None:
        result = _unavailable_result(request, generation_id, _NO_GENERATOR_REASON)
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    try:
        generation_directory.mkdir(parents=True, exist_ok=False)
        raw_output = generator.generate(request)
        output = (
            raw_output
            if isinstance(raw_output, DanceGeneratorOutput)
            else DanceGeneratorOutput.model_validate(raw_output)
        )
        video_dimensions = _validate_generator_output(output, request)
    except DanceGenerationError as exc:
        logger.warning(
            "Story-to-Dance generator rejected output: story_id=%s choreography_id=%s reason=%s",
            story_id,
            request.choreography_id,
            exc,
        )
        payload = _unavailable_result(request, generation_id, str(exc)).model_dump()
        payload["status"] = "failed"
        payload["error_code"] = exc.error_code
        result = DanceGenerationResult(**payload)
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    except ValidationError as exc:
        logger.warning(
            "Story-to-Dance generator output failed contract validation: story_id=%s choreography_id=%s errors=%s",
            story_id,
            request.choreography_id,
            exc.errors(include_input=False),
        )
        payload = _unavailable_result(
            request,
            generation_id,
            "The configured generator output did not satisfy the documented contract.",
        ).model_dump()
        payload["status"] = "failed"
        payload["error_code"] = "INVALID_GENERATION_OUTPUT"
        result = DanceGenerationResult(**payload)
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    except FileNotFoundError as exc:
        logger.warning(
            "Story-to-Dance generator checkpoint is unavailable: story_id=%s choreography_id=%s",
            story_id,
            request.choreography_id,
        )
        result = _unavailable_result(
            request,
            generation_id,
            "The configured generator checkpoint or required file is unavailable.",
            error_code="CHECKPOINT_UNAVAILABLE",
        )
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    except ImportError as exc:
        logger.warning(
            "Story-to-Dance generator dependencies are unavailable: story_id=%s choreography_id=%s reason=%s",
            story_id,
            request.choreography_id,
            exc,
        )
        result = _unavailable_result(
            request,
            generation_id,
            "The configured generator's required runtime dependencies are unavailable.",
            error_code="MODEL_UNAVAILABLE",
        )
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    except OSError as exc:
        logger.exception(
            "Story-to-Dance generation failed: story_id=%s choreography_id=%s",
            story_id,
            request.choreography_id,
        )
        payload = _unavailable_result(
            request,
            generation_id,
            "The configured generator failed while reading or producing its output.",
        ).model_dump()
        payload["status"] = "failed"
        payload["error_code"] = "GENERATION_FAILED"
        result = DanceGenerationResult(**payload)
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")
    except (RuntimeError, ValueError) as exc:
        logger.exception(
            "Story-to-Dance model execution failed: story_id=%s choreography_id=%s",
            story_id,
            request.choreography_id,
        )
        payload = _unavailable_result(
            request,
            generation_id,
            f"The configured motion generator failed during execution: {exc}",
            error_code="GENERATION_FAILED",
        ).model_dump()
        payload["status"] = "failed"
        result = DanceGenerationResult(**payload)
        _persist(settings.results_dir, result)
        return result.model_dump(mode="json")

    result = DanceGenerationResult(
        generation_id=generation_id,
        story_id=story_id,
        dance_plan_id=dance_plan_id,
        choreography_id=request.choreography_id,
        status="completed",
        fps=output.fps,
        duration_seconds=output.duration_seconds,
        video_width=video_dimensions["width"],
        video_height=video_dimensions["height"],
        frame_count=len(output.pose_sequence),
        skeleton_format=output.skeleton_format,
        coordinate_convention=output.coordinate_convention,
        pose_sequence=output.pose_sequence,
        video_url=(
            f"/api/story-to-dance/stories/{story_id}/plans/{dance_plan_id}/choreographies/"
            f"{request.choreography_id}/generations/{generation_id}/video"
        ),
        scene_timings=[
            DanceGenerationSceneTiming(
                scene_id=scene.scene_id,
                scene_order=scene.scene_order,
                start_time_seconds=scene.start_frame_index / output.fps,
                end_time_seconds=(scene.end_frame_index + 1) / output.fps,
            )
            for scene in output.scenes
            if scene.status == "generated"
        ],
        movement_coverage=DanceMovementCoverage(
            generated_scenes=sum(scene.status == "generated" for scene in output.scenes),
            total_scenes=len(output.scenes),
            source_supported_scenes=sum(
                any(
                    concept.mapping_status == "supported_concept"
                    for concept in scene.movement_concept
                )
                for scene in request.scenes
            ),
        ),
        generator_name=output.generator_name,
        generator_version=output.generator_version,
        visualization_type="rigged_3d_humanoid",
        scenes=[
            DanceGenerationSceneStatus(
                scene_id=scene.scene_id,
                scene_order=scene.scene_order,
                status=scene.status,
                generator_label=None,
                mapping_status=source_scene.mapping_status,
                movement_concepts=[
                    concept.concept
                    for concept in source_scene.movement_concept
                    if concept.mapping_status == "supported_concept"
                ],
                candidate_adavu=None,
                movement_sequence=scene.movement_sequence,
                mudra=scene.mudra,
                action=scene.action,
                target=scene.target,
                direction=scene.direction,
                transition=scene.transition,
                expressive_state=scene.expressive_state,
                source_provenance=source_scene.source_provenance,
                start_frame_index=scene.start_frame_index,
                end_frame_index=scene.end_frame_index,
                start_time_seconds=(
                    scene.start_frame_index / output.fps
                    if scene.status == "generated"
                    else None
                ),
                end_time_seconds=(
                    (scene.end_frame_index + 1) / output.fps
                    if scene.status == "generated"
                    else None
                ),
                reason=scene.reason,
            )
            for scene, source_scene in zip(output.scenes, request.scenes)
        ],
        provenance=[
            output.generator_name,
            output.repository,
            f"License: {output.license}",
            *output.provenance,
        ],
        limitations=list(_OUTPUT_LIMITATIONS),
    )
    _persist(settings.results_dir, result)
    return result.model_dump(mode="json")


def get_dance_performance_video(
    story_id: str,
    dance_plan_id: str,
    choreography_id: str,
    generation_id: str,
) -> Path:
    try:
        story_id = str(uuid.UUID(story_id))
        dance_plan_id = str(uuid.UUID(dance_plan_id))
        choreography_id = str(uuid.UUID(choreography_id))
        generation_id = str(uuid.UUID(generation_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise AppError("Generation identity is invalid.", 400, "INVALID_GENERATION_ID") from exc
    result_directory = _generation_path(
        settings.results_dir,
        story_id,
        generation_id,
    )
    result_path = result_directory / "result.json"
    if not result_path.is_file():
        raise AppError("Dance performance video was not found.", 404, "GENERATION_NOT_FOUND")
    try:
        record = load_json(result_path)
    except (OSError, ValueError) as exc:
        logger.exception(
            "Story-to-Dance generation metadata could not be read: story_id=%s generation_id=%s",
            story_id,
            generation_id,
        )
        raise AppError("Dance generation metadata is unavailable.", 500, "GENERATION_STORE_UNAVAILABLE") from exc
    if (
        not isinstance(record, dict)
        or record.get("story_id") != story_id
        or record.get("dance_plan_id") != dance_plan_id
        or record.get("choreography_id") != choreography_id
        or record.get("generation_id") != generation_id
        or record.get("status") != "completed"
    ):
        raise AppError("Dance performance video is unavailable.", 404, "GENERATION_VIDEO_UNAVAILABLE")
    current_story = get_story(story_id)
    current_plan = current_story.get("dance_plan")
    if (
        not isinstance(current_plan, dict)
        or current_plan.get("dance_plan_id") != dance_plan_id
        or current_plan.get("choreography_id") != choreography_id
    ):
        raise AppError("The requested generation is stale.", 404, "STALE_GENERATION")
    video_path = (result_directory / "dance-performance.mp4").resolve()
    expected_directory = result_directory.resolve()
    if (
        video_path.parent != expected_directory
        or not video_path.is_file()
        or video_path.stat().st_size == 0
    ):
        raise AppError("Dance performance video is unavailable.", 404, "GENERATION_VIDEO_UNAVAILABLE")
    return video_path
