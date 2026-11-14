"""Typed schemas for evidence-grounded story generation."""
from pydantic import BaseModel


class StoryRequest(BaseModel):
    language: str = "en"
    provider: str | None = None


class StoryInterpretationItem(BaseModel):
    id: str
    statement: str
    supporting_evidence: list[str]
    confidence: float | None = None
    status: str = "evidence_supported"
    knowledge_status: str | None = None
    verification_status: str | None = None
    claim_id: str | None = None
    source_references: list[str] | None = None
    uncertainty_notes: list[str] | None = None


class StoryResponse(BaseModel):
    analysis_id: str
    status: str
    language: str
    title: str | None = None
    story: str | None = None
    interpretations: list[StoryInterpretationItem]
    supporting_evidence: list[str]
    unresolved_evidence: list[str]
    message: str | None = None
    provider: str | None = None
    model: str | None = None
    generation_method: str | None = None
    narrative_confidence: str | None = None
    evidence_coverage: dict[str, int | bool] | None = None


class NarrativeGenerationResponse(BaseModel):
    """Phase 6 response contract served by the Story route."""
    schema_version: str
    analysis_id: str
    video_id: str
    mode: str
    status: str
    language: str = "en"
    presentation_version: str | None = None
    title: str | None = None
    narrative: str | None = None
    evidence_coverage: float
    used_event_ids: list[str]
    limitations: list[str]
    provider: str
    model: str
    message: str | None = None
    retry_after_seconds: int | None = None
    error_code: str | None = None
    package_eligible: bool = False
    package_fingerprint: str | None = None
    package_evidence_coverage: float = 0.0
