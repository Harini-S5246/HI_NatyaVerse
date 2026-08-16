from pydantic import BaseModel


class BhavaFramePrediction(BaseModel):
    frame_number: int
    timestamp: float
    filename: str
    bhava: str
    confidence: float


class BhavaEvent(BaseModel):
    bhava: str
    start_time: float
    end_time: float
    confidence: float
    frame_count: int


class BhavaSummary(BaseModel):
    unique_bhava_count: int
    dominant_bhava: str | None
    average_confidence: float


class BhavaDetection(BaseModel):
    name: str
    confidence: float | None = None
    timestamps: list[float] | None = None


class BhavaSegment(BaseModel):
    label: str
    start: float
    end: float
    confidence: float


class BhavaClassificationResponse(BaseModel):
    analysis_id: str
    video_id: str
    status: str
    frame_count: int
    prediction_count: int
    bhava_events: list[BhavaEvent]
    frames: list[BhavaFramePrediction]
    summary: BhavaSummary
    bhava: dict | None = None
    evidence: dict | None = None