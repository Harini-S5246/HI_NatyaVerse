from __future__ import annotations
import logging
from app.config import settings
from app.models.bhava_model import BhavaModel
from app.models.mudra_model import MudraModel
from app.models.pose_model import PoseModel

logger = logging.getLogger(__name__)

class ModelManager:
    def __init__(self) -> None:
        self.models = {
            "mudra": MudraModel(settings.mudra_model_path, settings.mudra_classes_path),
            "bhava": BhavaModel(settings.bhava_model_path, settings.bhava_metadata_path),
            "pose": PoseModel(settings.pose_model_path, settings.pose_classes_path),
        }

    def status(self) -> dict:
        report = {}
        for name, adapter in self.models.items():
            report[name] = adapter.status()
        return report

    def missing_models(self) -> list[str]:
        return [name for name, info in self.status().items() if not info["loaded"]]

    def get(self, name: str):
        adapter = self.models[name]
        if not adapter.load():
            raise RuntimeError(adapter.load_error or f"{name} model unavailable")
        return adapter

model_manager = ModelManager()
