from fastapi import APIRouter, Query
from app.core.errors import AppError
from app.services.result_service import get_result, list_results

router = APIRouter(prefix="/api", tags=["Results"])

@router.get("/results")
def results() -> dict:
    return {"results": list_results()}

@router.get("/results/{result_id}")
def result(result_id: str) -> dict:
    return get_result(result_id)

@router.get("/story/{analysis_id}")
def story(analysis_id: str, language: str = Query("English"), all_languages: bool = False) -> dict:
    data = get_result(analysis_id)
    story_data = data.get("story")
    if not story_data or story_data.get("status") == "not_generated":
        raise AppError("No generated story is available for this analysis.", 404, "STORY_NOT_FOUND")
    return story_data
