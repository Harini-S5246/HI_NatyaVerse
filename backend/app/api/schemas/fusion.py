"""Typed response schemas for multimodal fusion output."""
from pydantic import BaseModel, Field


class FusionTimelineEntry(BaseModel):
    start_time: float
    end_time: float
    mudra: str | None = None
    mudra_confidence: float | None = None
    mudra_grounded: bool = False
    mudra_knowledge_status: str | None = None
    mudra_verification_status: str | None = None
    mudra_claim_id: str | None = None
    mudra_source_references: list[str] = Field(default_factory=list)
    mudra_uncertainty_notes: list[str] = Field(default_factory=list)
    bhava: str | None = None
    bhava_confidence: float | None = None


class FusionSummary(BaseModel):
    dominant_mudra: str | None = None
    dominant_bhava: str | None = None
    mudra_event_count: int = 0
    bhava_event_count: int = 0
    average_mudra_confidence: float | None = None
    average_bhava_confidence: float | None = None
    frame_count: int = 0


class FusionResponse(BaseModel):
    analysis_id: str
    status: str = "completed"
    timeline: list[FusionTimelineEntry]
    summary: FusionSummary
    evidence: dict | None = None
    mudra_bhava_alignment: dict | None = None
    cultural_knowledge_evidence: list[dict] | None = None