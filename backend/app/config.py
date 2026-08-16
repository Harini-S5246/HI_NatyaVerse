"""Application configuration loaded from environment variables."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = BACKEND_DIR / "models"
def _path_from_env(name: str, default: Path | None = None) -> Path | None:
    value = os.getenv(name, "").strip()
    if value:
        path = Path(value)
        return path if path.is_absolute() else BACKEND_DIR.parent / path
    return default

@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    cors_origins: tuple[str, ...] = tuple(item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip())
    upload_dir: Path = _path_from_env("UPLOAD_DIR", BACKEND_DIR / "uploads")  # type: ignore[arg-type]
    frame_output_dir: Path = _path_from_env("FRAME_OUTPUT_DIR", BACKEND_DIR / "frames")  # type: ignore[arg-type]
    results_dir: Path = _path_from_env("RESULTS_DIR", BACKEND_DIR / "results")  # type: ignore[arg-type]
    mudra_model_path: Path | None = _path_from_env("MUDRA_MODEL_PATH", MODELS_DIR / "mudra" / "Natya_Mudra_EfficientNetB0_FineTuned.keras")
    bhava_model_path: Path | None = _path_from_env("BHAVA_MODEL_PATH", MODELS_DIR / "bhava" / "bhava_phase3_moderated_best.keras")
    pose_model_path: Path | None = _path_from_env("POSE_MODEL_PATH", MODELS_DIR / "pose" / "Natya_Pose_BiLSTM_Best.keras")
    pose_classes_path: Path | None = _path_from_env("POSE_CLASSES_PATH", MODELS_DIR / "pose" / "pose_class_names.json")
    mudra_classes_path: Path | None = _path_from_env("MUDRA_CLASSES_PATH", MODELS_DIR / "mudra" / "mudra_class_names.json")
    bhava_metadata_path: Path | None = _path_from_env("BHAVA_METADATA_PATH", MODELS_DIR / "bhava" / "bhava_model_metadata.json")
    mudra_knowledge_path: Path | None = _path_from_env("MUDRA_KNOWLEDGE_PATH", BACKEND_DIR / "app" / "data" / "knowledge" / "mudra_knowledge.json")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.frame_output_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

settings = Settings()
