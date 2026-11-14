"""Readily identifiable synthetic Story demonstration endpoint."""
from fastapi import APIRouter

from app.services.demonstration_service import generate_demonstration_story


router = APIRouter(prefix="/api/demonstration", tags=["Demonstration"])


@router.post("/story")
def demonstration_story() -> dict:
    return generate_demonstration_story()
