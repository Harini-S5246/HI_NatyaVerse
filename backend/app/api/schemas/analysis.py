from pydantic import BaseModel


class ModelUnavailableResponse(BaseModel):
    status: str = "model_unavailable"
    message: str
    missing_models: list[str]
