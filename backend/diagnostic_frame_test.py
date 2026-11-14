"""SAFE diagnostic script (not part of the app) to test frame-level model
predictions directly, bypassing the API layer, to determine whether the
underlying models produce different predictions across frames and across
videos. No secrets are printed. This file is temporary and for
investigation only; it can be deleted after the investigation.
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, ".")
from app.models.model_manager import model_manager  # noqa: E402

VIDEOS = [
    "0b1c2d39-a7c8-4d97-aff2-b08e166126a4",
    "59afda6d-9159-4f75-bf2d-a0072ae2febd",
]

FRAME_INDICES = [0, 1, 2, 5, 10, 30, 60, 90]


def top3(probabilities: dict) -> list:
    return sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)[:3]


def run_for_video(video_id: str, model_name: str):
    model = model_manager.get(model_name)
    print(f"\n=== {model_name.upper()} predictions for video_id={video_id} ===")
    for idx in FRAME_INDICES:
        filename = f"frames/{video_id}/frame_{idx:06d}.jpg"
        frame = cv2.imread(filename)
        if frame is None:
            print(f"{filename}: NOT FOUND, skipping")
            continue
        pred = model.predict(frame)
        t3 = top3(pred["probabilities"])
        print(
            f"{filename} (shape={frame.shape}) -> label={pred['label']} "
            f"confidence={pred['confidence']:.4f} top3={t3}"
        )


if __name__ == "__main__":
    for video_id in VIDEOS:
        run_for_video(video_id, "mudra")
        run_for_video(video_id, "bhava")
