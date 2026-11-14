"""Application configuration loaded from environment variables."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
_GEMINI_API_KEY_WAS_IN_PROCESS = "GEMINI_API_KEY" in os.environ
_GOOGLE_API_KEY_FROM_PROCESS = os.getenv("GOOGLE_API_KEY", "").strip()
# Load backend/.env (secrets live ONLY here, never in source or frontend).
load_dotenv(BACKEND_DIR / ".env")
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
    rigged_dancer_asset_path: Path | None = _path_from_env("RIGGED_DANCER_ASSET_PATH")
    mudra_model_path: Path | None = _path_from_env("MUDRA_MODEL_PATH", MODELS_DIR / "mudra" / "Natya_Mudra_EfficientNetB0_FineTuned.keras")
    bhava_model_path: Path | None = _path_from_env("BHAVA_MODEL_PATH", MODELS_DIR / "bhava" / "bhava_phase3_moderated_best.keras")
    pose_model_path: Path | None = _path_from_env("POSE_MODEL_PATH", MODELS_DIR / "pose" / "Natya_Pose_BiLSTM_Best.keras")
    pose_classes_path: Path | None = _path_from_env("POSE_CLASSES_PATH", MODELS_DIR / "pose" / "pose_class_names.json")
    mudra_classes_path: Path | None = _path_from_env("MUDRA_CLASSES_PATH", MODELS_DIR / "mudra" / "mudra_class_names.json")
    bhava_metadata_path: Path | None = _path_from_env("BHAVA_METADATA_PATH", MODELS_DIR / "bhava" / "bhava_model_metadata.json")
    mudra_knowledge_path: Path | None = _path_from_env("MUDRA_KNOWLEDGE_PATH", BACKEND_DIR / "app" / "data" / "knowledge" / "mudra_knowledge.json")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
    dance_reference_min_confidence: float = float(os.getenv("DANCE_REFERENCE_MIN_CONFIDENCE", "0.65"))
    # --- LLM / story generation -----------------------------------------
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    story_primary_provider: str = os.getenv("STORY_PRIMARY_PROVIDER", "gemini").strip().lower()
    story_secondary_provider: str = os.getenv("STORY_SECONDARY_PROVIDER", "").strip().lower()
    # The live Story boundary selects Gemini unless a non-production test
    # explicitly injects a different provider through the neutral interface.
    story_llm_provider: str = os.getenv("STORY_LLM_PROVIDER", "gemini").strip().lower()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.frame_output_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

settings = Settings()


def _safe_key_fingerprint(value: str) -> str:
    if not value:
        return "absent"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]}"


_gemini_key_source = (
    "process_environment"
    if _GEMINI_API_KEY_WAS_IN_PROCESS
    else "backend/.env"
    if settings.gemini_api_key
    else "missing"
)
print(
    "[GEMINI_KEY_DIAGNOSTIC] "
    f"present={bool(settings.gemini_api_key)} "
    f"fingerprint={_safe_key_fingerprint(settings.gemini_api_key)} "
    f"source={_gemini_key_source} "
    f"google_api_key_present={bool(_GOOGLE_API_KEY_FROM_PROCESS)}"
)
