"""Contracts for a pluggable, provenance-bearing dance generator."""
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.api.schemas.story_to_dance import (
    BharatanatyamConcept,
    BhavaMapping,
    MovementIntent,
    MovementSourceProvenance,
    MudraMapping,
    StoryToDanceRecord,
)


class StoryDanceGenerationScene(BaseModel):
    scene_id: str
    scene_order: int = Field(gt=0)
    source_text: str
    action: str
    objects: list[str] = Field(default_factory=list)
    location: str | None = None
    movement_intent: MovementIntent = Field(default_factory=MovementIntent)
    mudra: list[MudraMapping]
    bhava: list[BhavaMapping]
    movement_concept: list[BharatanatyamConcept]
    visualization_sequence: list[str] = Field(default_factory=list)
    candidate_adavu: None
    mapping_status: Literal["supported_concept", "review_required"]
    source_provenance: list[MovementSourceProvenance]
    generator_label: str | None
    duration_seconds: float | None


class StoryDanceGenerationRequest(BaseModel):
    generation_id: str
    story_id: str
    dance_plan_id: str
    choreography_id: str
    output_directory: Path
    scenes: list[StoryDanceGenerationScene]


class GeneratorPoseFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    pose_data: dict[str, Any]


class GeneratorSceneResult(BaseModel):
    scene_id: str
    scene_order: int = Field(gt=0)
    status: Literal["generated", "unavailable", "review_required"]
    generator_label: str | None
    movement_sequence: list[str] = Field(default_factory=list)
    mudra: list[str] = Field(default_factory=list)
    action: str
    target: str | None = None
    direction: str | None = None
    transition: str
    expressive_state: Literal[
        "neutral", "respectful", "admiration", "attention", "graceful"
    ]
    start_frame_index: int | None = Field(default=None, ge=0)
    end_frame_index: int | None = Field(default=None, ge=0)
    reason: str | None = None


class DanceGeneratorOutput(BaseModel):
    generation_id: str
    story_id: str
    dance_plan_id: str
    choreography_id: str
    fps: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    video_width: int | None = Field(default=None, gt=0)
    video_height: int | None = Field(default=None, gt=0)
    skeleton_format: str = Field(min_length=1)
    coordinate_convention: str = Field(min_length=1)
    pose_sequence: list[GeneratorPoseFrame] = Field(min_length=1)
    video_path: Path
    scenes: list[GeneratorSceneResult] = Field(min_length=1)
    generator_name: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    license: str = Field(min_length=1)
    provenance: list[str] = Field(min_length=1)


class DanceGenerationSceneStatus(BaseModel):
    scene_id: str
    scene_order: int
    status: Literal["generated", "unavailable", "review_required"]
    generator_label: str | None
    mapping_status: Literal["supported_concept", "review_required"]
    movement_concepts: list[str]
    candidate_adavu: None
    movement_sequence: list[str]
    mudra: list[str]
    action: str
    target: str | None
    direction: str | None = None
    transition: str
    expressive_state: Literal[
        "neutral", "respectful", "admiration", "attention", "graceful"
    ]
    source_provenance: list[MovementSourceProvenance]
    start_frame_index: int | None = None
    end_frame_index: int | None = None
    start_time_seconds: float | None = Field(default=None, ge=0)
    end_time_seconds: float | None = Field(default=None, gt=0)
    reason: str | None = None


class DanceGenerationSceneTiming(BaseModel):
    scene_id: str
    scene_order: int
    start_time_seconds: float = Field(ge=0)
    end_time_seconds: float = Field(gt=0)


class DanceMovementCoverage(BaseModel):
    generated_scenes: int = Field(ge=0)
    total_scenes: int = Field(gt=0)
    source_supported_scenes: int = Field(ge=0)


class DanceGenerationResult(BaseModel):
    generation_id: str
    story_id: str
    dance_plan_id: str
    choreography_id: str
    status: Literal["completed", "unavailable", "failed"]
    fps: float | None = None
    duration_seconds: float | None = None
    video_width: int | None = Field(default=None, gt=0)
    video_height: int | None = Field(default=None, gt=0)
    frame_count: int | None = Field(default=None, gt=0)
    skeleton_format: str | None = None
    coordinate_convention: str | None = None
    pose_sequence: list[GeneratorPoseFrame] | None = None
    video_url: str | None = None
    scene_timings: list[DanceGenerationSceneTiming] = Field(default_factory=list)
    movement_coverage: DanceMovementCoverage
    generator_name: str | None = None
    generator_version: str | None = None
    visualization_type: Literal["procedural_dancer_avatar", "rigged_3d_humanoid"] | None = None
    scenes: list[DanceGenerationSceneStatus]
    provenance: list[str]
    reason: str | None = None
    error_code: Literal[
        "MODEL_UNAVAILABLE",
        "CHECKPOINT_UNAVAILABLE",
        "GENERATION_FAILED",
        "VIDEO_RENDER_FAILED",
        "VIDEO_VALIDATION_FAILED",
        "STALE_GENERATION",
        "INVALID_GENERATION_OUTPUT",
    ] | None = None
    limitations: list[str]

    @model_validator(mode="after")
    def validate_completed_result(self) -> "DanceGenerationResult":
        if [scene.scene_order for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("Generation scene order must be contiguous and one-based.")
        if len({scene.scene_id for scene in self.scenes}) != len(self.scenes):
            raise ValueError("Generation scene IDs must be unique.")
        if (
            self.movement_coverage.generated_scenes
            != sum(scene.status == "generated" for scene in self.scenes)
            or self.movement_coverage.total_scenes != len(self.scenes)
            or self.movement_coverage.source_supported_scenes
            != sum(bool(scene.movement_concepts) for scene in self.scenes)
        ):
            raise ValueError("Scene coverage must match rendered and source-supported scenes.")
        if self.status == "completed":
            if (
                not self.video_url
                or not self.pose_sequence
                or self.fps is None
                or self.duration_seconds is None
                or self.frame_count is None
                or not self.scene_timings
                or not self.generator_name
                or not self.generator_version
                or self.visualization_type not in {"procedural_dancer_avatar", "rigged_3d_humanoid"}
                or not self.skeleton_format
                or not self.coordinate_convention
                or not self.provenance
            ):
                raise ValueError("Completed generation requires validated pose and video metadata.")
            if self.frame_count != len(self.pose_sequence or []):
                raise ValueError("Completed generation frame count must match the pose sequence.")
            generated_scenes = [scene for scene in self.scenes if scene.status == "generated"]
            if [
                (timing.scene_id, timing.scene_order)
                for timing in self.scene_timings
            ] != [
                (scene.scene_id, scene.scene_order)
                for scene in generated_scenes
            ]:
                raise ValueError("Scene timings must match generated scenes in order.")
            if any(
                scene.start_frame_index is None
                or scene.end_frame_index is None
                or scene.start_time_seconds is None
                or scene.end_time_seconds is None
                for scene in generated_scenes
            ):
                raise ValueError("Generated scenes require measured frame/time ranges.")
            if any(scene.candidate_adavu is not None for scene in self.scenes):
                raise ValueError("The procedural avatar cannot assign an unvalidated Adavu.")
            if any(
                timing.end_time_seconds > (self.duration_seconds or 0)
                for timing in self.scene_timings
            ):
                raise ValueError("Scene timings cannot extend beyond video duration.")
        elif self.video_url is not None:
            raise ValueError("Unavailable or failed generation cannot include a video URL.")
        return self


class StoryToDanceWorkflowResponse(BaseModel):
    story: StoryToDanceRecord
    generation: DanceGenerationResult
