from fastapi import APIRouter
from app.models.model_manager import model_manager

router = APIRouter(prefix="/api", tags=["Health"])

@router.get("/health")
def health() -> dict:
    return {"status": "ok", "models": model_manager.status()}

@router.get("/health/models")
def model_health() -> dict:
    """Load each configured model once, then report its runtime metadata."""
    return model_manager.status()
