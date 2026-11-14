"""Contracts for the isolated Story-to-Dance workflow."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StoryToDanceStoryRequest(BaseModel):
    story_text: str
    language: str = "en"
    title: str | None = None


class StoryToDanceWorkflowRequest(StoryToDanceStoryRequest):
    request_id: UUID


class MudraMapping(BaseModel):
    concept: str
    mudra: str | None = None
    meaning: str | None = None
    source: str | None = None
    status: Literal["mapped", "unsupported", "knowledge_unavailable"]
    note: str | None = None


class BhavaMapping(BaseModel):
    expressive_quality: str
    bhava: str | None = None
    status: Literal["unmapped"]
    note: str


class MovementIntentAction(BaseModel):
    action: str
    target: str | None = None
    direction: str | None = None
    movement_type: str
    movement_concept: str | None = None
    candidate_adavu: None = None
    status: Literal["supported", "review_required"]
    mapping_status: Literal["supported_concept", "review_required"]
    source: str | None = None
    source_reference: str | None = None
    mapping_reason: str
    review_required: bool


class MovementIntent(BaseModel):
    action: str = ""
    target: str | None = None
    direction: str | None = None
    actions: list[MovementIntentAction] = Field(default_factory=list)
    movement_name: str | None = None
    movement_type: str | None = None
    status: Literal["supported", "review_required", "unavailable"] = "review_required"
    source: str | None = None
    source_reference: str | None = None
    movement_concept: str | None = None
    candidate_adavu: str | None = None
    mapping_status: Literal["supported_concept", "review_required", "unavailable"] = "review_required"
    mapping_reason: str | None = None
    source_quote: str | None = None
    review_required: bool = True


class BharatanatyamConcept(BaseModel):
    action: str
    direction: str | None = None
    concept: str
    candidate_adavu: None = None
    mapping_status: Literal["supported_concept"]
    source: str
    source_reference: str
    mapping_reason: str


class MovementSourceProvenance(BaseModel):
    concept: str
    source: str
    source_reference: str
    notes: str


class MovementVocabulary(BaseModel):
    status: Literal["supported", "review_required", "unavailable"] = "unavailable"
    message: str = "NO CURATED MOVEMENT RESOURCE FOUND"
    entries: list[dict[str, str | list[str] | None]] = Field(default_factory=list)
    source: str | None = None
    supported_actions: list[str] = Field(default_factory=list)
    supported_intents: list[str] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)


class MovementMapping(BaseModel):
    action_type: str
    movement_primitive: str | None = None
    adavu: str | None = None
    pose: str | None = None
    status: Literal["review_required"]
    note: str
    movement_intent: MovementIntent | None = None
    movement_name: str | None = None
    movement_source: str | None = None
    movement_vocabulary: MovementVocabulary | None = None


class SceneDanceMapping(BaseModel):
    mudra_status: Literal["mapped", "unsupported", "knowledge_unavailable"]
    mudras: list[MudraMapping]
    bhava: list[BhavaMapping]
    movement: MovementMapping


class DanceScene(BaseModel):
    scene_id: str
    story_id: str
    order: int
    scene_order: int
    characters: list[str]
    character: list[str]
    action_type: str
    action_text: str
    action: str
    objects: list[str]
    location: str | None = None
    expressive_qualities: list[str]
    expressions: list[str]
    narrative_text: str
    source_text: str
    duration_estimate_seconds: float | None = None
    mudra: list[MudraMapping]
    bhava: list[BhavaMapping]
    visualization_sequence: list[str] = Field(default_factory=list)
    movement_intent: MovementIntent
    bharatanatyam_concept: list[BharatanatyamConcept]
    candidate_adavu: None = None
    mapping_status: Literal["supported_concept", "review_required"]
    source_provenance: list[MovementSourceProvenance]
    generator_label: str | None = None
    generation_status: Literal["unavailable"]
    dance_mapping: SceneDanceMapping


class ChoreographyStep(BaseModel):
    step_id: str
    scene_id: str
    order: int
    characters: list[str]
    source_quote: str = ""
    story_action: str
    objects: list[str] = Field(default_factory=list)
    location: str | None = None
    source_expressions: list[str] = Field(default_factory=list)
    mudras: list[MudraMapping] = Field(default_factory=list)
    bhava: list[BhavaMapping] = Field(default_factory=list)
    visualization_sequence: list[str] = Field(default_factory=list)
    movement_primitive: None = None
    adavu: None = None
    pose: None = None
    movement_status: Literal["review_required"]
    movement_note: str = "Movement mapping requires choreographer review."
    movement_intent: MovementIntent | None = None
    movement_name: str | None = None
    movement_source: str | None = None
    movement_vocabulary: MovementVocabulary | None = None
    transition: dict[str, str]


class PoseSequence(BaseModel):
    status: Literal["not_generated"]
    items: list[dict[str, str]]
    message: str


class GeneratedPerformance(BaseModel):
    status: Literal["not_generated"]
    video_url: None = None
    message: str


class DancePlan(BaseModel):
    story_id: str
    dance_plan_id: str
    choreography_id: str
    title: str
    language: str
    summary: str
    status: Literal["ready"]
    scenes: list[DanceScene]
    choreography: list[ChoreographyStep]
    movement_vocabulary: MovementVocabulary | None = None
    pose_sequence: PoseSequence
    generated_performance: GeneratedPerformance
    limitations: list[str]


class StoryToDanceRecord(BaseModel):
    story_id: str
    title: str
    language: str
    story_text: str
    status: Literal["ready_for_planning", "plan_ready"]
    created_at: str
    dance_plan: DancePlan | None = None

