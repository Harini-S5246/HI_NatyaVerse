"""Local verification for the three trained HI-NATYA-VERSE models.

Run from the backend directory with the project's Python environment.  This
script only loads existing artifacts and executes zero-valued test inputs; it
never trains, downloads, or writes model files.
"""
from __future__ import annotations

import sys

import numpy as np

from app.models.model_manager import model_manager


def verify_probabilities(name: str, prediction: dict) -> None:
    values = np.asarray(list(prediction["probabilities"].values()), dtype=np.float32)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise RuntimeError(f"{name}: output is not a valid non-negative probability vector.")
    if not np.isclose(values.sum(), 1.0, atol=1e-3):
        raise RuntimeError(f"{name}: probabilities sum to {values.sum():.6f}, not 1.0.")
    print(f"{name}: valid probabilities (sum={values.sum():.6f})")


def main() -> int:
    adapters = {name: model_manager.get(name) for name in ("mudra", "pose", "bhava")}
    for name, adapter in adapters.items():
        print(f"{name} model path: {adapter.model_path}")
        print(f"{name} input shape: {adapter.input_shape}")
        print(f"{name} output shape: {adapter.output_shape}")
        print(f"{name} class count: {len(adapter.class_names or [])}")

    image = np.zeros((224, 224, 3), dtype=np.uint8)  # BGR frame; adapters convert to RGB.
    verify_probabilities("mudra", adapters["mudra"].predict(image))
    verify_probabilities("bhava", adapters["bhava"].predict(image))

    pose_shape = tuple(adapters["pose"].input_shape[1:])
    verify_probabilities("pose", adapters["pose"].predict_sequence(np.zeros(pose_shape, dtype=np.float32)))
    print("All trained model checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Model verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
