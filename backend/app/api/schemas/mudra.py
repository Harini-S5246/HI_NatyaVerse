from pydantic import BaseModel, Field


class MudraFramePrediction(BaseModel):
    frame_number: int
    timestamp: float
    filename: str
    mudra: str
    confidence: float
    grounded: bool = False
    meaning: str | None = None
    status: str = "unresolved"
    knowledge_status: str | None = None
    verification_status: str | None = None
    claim_id: str | None = None
    source_references: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    uncertainty_reason: str | None = None


class MudraEvent(BaseModel):
    mudra: str
    start_time: float
    end_time: float
    confidence: float
    frame_count: int


class MudraDetection(BaseModel):
    name: str
    confidence: float | None = None
    grounded: bool = False
    status: str = "unresolved"
    knowledge_status: str | None = None
    meaning: str | None = None
    timestamps: list[float] | None = None
    verification_status: str | None = None
    claim_id: str | None = None
    source_references: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    uncertainty_reason: str | None = None


class MudraSummary(BaseModel):
    unique_mudra_count: int
    dominant_mudra: str | None
    average_confidence: float


class MudraClassificationResponse(BaseModel):
    video_id: str
    frame_count: int
    prediction_count: int
    mudra_events: list[MudraEvent]
    frames: list[MudraFramePrediction]
    summary: MudraSummary
    grounded_count: int = 0
    unresolved_count: int = 0
    mudra: dict | None = None
    evidence: dict | None = None
    temporal_sequence: dict | None = None
