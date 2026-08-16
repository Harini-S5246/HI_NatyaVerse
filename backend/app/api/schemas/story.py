"""Typed schemas for evidence-grounded story generation."""
from pydantic import BaseModel


class StoryRequest(BaseModel):
    language: str = "en"


class StoryInterpretationItem(BaseModel):
    id: str
    statement: str
    supporting_evidence: list[str]
    confidence: float | None = None
    status: str = "evidence_supported"


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