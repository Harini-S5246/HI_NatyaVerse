from pathlib import Path
from app.models.base import KerasImageModel
from app.utils.json_utils import load_json

BHAVA_CLASSES = ["Angry", "Disgust", "Fear", "Happy", "Sad", "Surprise", "Neutral"]

class BhavaModel(KerasImageModel):
    def __init__(self, model_path: Path | None, metadata_path: Path | None):
        super().__init__(model_path, metadata_path)

    def _load_class_names(self) -> list[str]:
        if not self.classes_path or not self.classes_path.is_file():
            raise FileNotFoundError(f"Bhava metadata file is missing: {self.classes_path}")
        classes = load_json(self.classes_path).get("classes")
        if classes != BHAVA_CLASSES:
            raise ValueError("Bhava class order must be Angry, Disgust, Fear, Happy, Sad, Surprise, Neutral.")
        return classes
