from pathlib import Path
from app.models.base import KerasImageModel

class MudraModel(KerasImageModel):
    """Adapter for Natya_Mudra_EfficientNetB0_91_82.keras; class names are external metadata."""
    def __init__(self, model_path: Path | None, classes_path: Path | None):
        super().__init__(model_path, classes_path)
