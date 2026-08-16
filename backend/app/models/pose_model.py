from pathlib import Path
import numpy as np
from app.models.base import KerasImageModel

class PoseModel(KerasImageModel):
    """BiLSTM adapter for a sequence of 20 pose-landmark vectors of length 132."""
    def __init__(self, model_path: Path | None, classes_path: Path | None):
        super().__init__(model_path, classes_path)

    def preprocess(self, landmark_sequence) -> np.ndarray:
        sequence = np.asarray(landmark_sequence, dtype=np.float32)
        expected = tuple(self.input_shape[1:]) if self.input_shape else (20, 132)
        if sequence.shape == expected:
            return np.expand_dims(sequence, axis=0)
        if sequence.shape == (1, *expected):
            return sequence
        raise ValueError(f"Pose model expects landmark data shaped {expected}; received {sequence.shape}.")

    def predict_sequence(self, landmark_sequence) -> dict:
        return self.predict(landmark_sequence)
