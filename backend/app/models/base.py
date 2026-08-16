from __future__ import annotations
from pathlib import Path
from threading import Lock
from typing import Any

from app.utils.image_utils import prepare_image
from app.utils.json_utils import load_json


class KerasImageModel:
    def __init__(self, model_path: Path | None, classes_path: Path | None = None):
        self.model_path, self.classes_path, self.model, self.load_error = model_path, classes_path, None, None
        self.class_names: list[str] | None = None
        self._load_lock = Lock()

    def load(self) -> bool:
        if self.model is not None:
            return True
        with self._load_lock:
            if self.model is not None:
                return True
            if not self.model_path:
                self.load_error = "Model path is not configured."
                return False
            if not self.model_path.is_file():
                self.load_error = f"Model file is missing: {self.model_path}"
                return False
            try:
                self.class_names = self._load_class_names()
                import tensorflow as tf
                self.model = tf.keras.models.load_model(self.model_path, compile=False)
                self._validate_model_classes()
                self.load_error = None
                return True
            except Exception as exc:
                self.load_error = f"Unable to load {self.model_path.name}: {exc}"
                self.model = None
                return False

    def _load_class_names(self) -> list[str] | None:
        if not self.classes_path:
            return self.class_names
        if not self.classes_path.is_file():
            raise FileNotFoundError(f"Class mapping file is missing: {self.classes_path}")
        raw = load_json(self.classes_path)
        names = raw if isinstance(raw, list) else raw.get("class_names")
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError(f"Invalid class mapping in {self.classes_path}")
        return names

    def _validate_model_classes(self) -> None:
        if self.class_names and self.output_shape[-1] != len(self.class_names):
            raise ValueError(
                f"Class mapping has {len(self.class_names)} labels, but model output has {self.output_shape[-1]} values."
            )

    @property
    def input_shape(self) -> list[Any] | None:
        return self._shape_as_list(getattr(self.model, "input_shape", None)) if self.model is not None else None

    @property
    def output_shape(self) -> list[Any] | None:
        return self._shape_as_list(getattr(self.model, "output_shape", None)) if self.model is not None else None

    @staticmethod
    def _shape_as_list(shape: Any) -> list[Any] | None:
        if isinstance(shape, (list, tuple)) and shape and isinstance(shape[0], (list, tuple)):
            shape = shape[0]
        return list(shape) if shape is not None else None

    def status(self) -> dict[str, Any]:
        loaded = self.load()
        return {
            "loaded": loaded,
            "model": str(self.model_path) if self.model_path else None,
            "class_mapping": str(self.classes_path) if self.classes_path else None,
            "input_shape": self.input_shape,
            "output_shape": self.output_shape,
            "classes": len(self.class_names or []),
            **({"error": self.load_error} if self.load_error else {}),
        }

    def preprocess(self, frame):
        return prepare_image(frame)

    def predict(self, frame) -> dict:
        if not self.load():
            raise RuntimeError(self.load_error or "Model unavailable")
        import numpy as np
        scores = np.asarray(self.model.predict(self.preprocess(frame), verbose=0))[0]
        index = int(np.argmax(scores))
        label = self.class_names[index] if self.class_names and index < len(self.class_names) else None
        probabilities = {self.class_names[i] if self.class_names and i < len(self.class_names) else str(i): float(value) for i, value in enumerate(scores)}
        return {"label": label, "class_index": index, "confidence": float(scores[index]), "probabilities": probabilities}
