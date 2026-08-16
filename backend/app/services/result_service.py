import csv
from pathlib import Path
from app.config import settings
from app.core.errors import AppError
from app.utils.json_utils import load_json, save_json

def result_path(result_id: str) -> Path:
    if not result_id.replace("-", "").isalnum():
        raise AppError("Invalid result id.", 400, "INVALID_RESULT_ID")
    return settings.results_dir / f"{result_id}.json"

def save_result(result: dict) -> None:
    save_json(result_path(result["analysis_id"]), result)

MODALITIES = {"mudra", "bhava", "fusion", "story"}


def modality_result_path(analysis_id: str, modality: str) -> Path:
    """Path for a modality-specific result, kept out of the top-level listing."""
    if not analysis_id.replace("-", "").isalnum():
        raise AppError("Invalid result id.", 400, "INVALID_RESULT_ID")
    if modality not in MODALITIES:
        raise AppError("Invalid modality.", 400, "INVALID_MODALITY")
    return settings.results_dir / "modalities" / f"{analysis_id}_{modality}.json"


def save_modality_result(analysis_id: str, modality: str, result: dict) -> None:
    """Persist one modality's result without overwriting the other modality."""
    save_json(modality_result_path(analysis_id, modality), result)


def get_modality_result(analysis_id: str, modality: str) -> dict:
    """Load a modality-specific result, raising a 404 when it does not exist."""
    path = modality_result_path(analysis_id, modality)
    if path.is_file():
        return load_json(path)
    raise AppError(
        f"{modality.capitalize()} result was not found for this video.",
        404,
        "MODALITY_RESULT_NOT_FOUND",
    )

def get_result(result_id: str) -> dict:
    path = result_path(result_id)
    if path.is_file():
        return load_json(path)
    csv_path = settings.results_dir / f"{result_id}.csv"
    if csv_path.is_file():
        # Imported Colab timeline CSVs remain available without making any
        # particular optional artifact (such as segment_summary) mandatory.
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return {"analysis_id": result_id, "video_id": result_id, "status": "completed", "timeline": rows, "dance_events": [], "story": {}, "metadata": {"source": csv_path.name}}
    raise AppError("Result not found.", 404, "RESULT_NOT_FOUND")

def list_results() -> list[dict]:
    files = [*settings.results_dir.glob("*.json"), *settings.results_dir.glob("*.csv")]
    return [{"result_id": item.stem, "format": item.suffix.removeprefix(".")} for item in sorted(files, reverse=True)]
