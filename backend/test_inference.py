#!/usr/bin/env python3
"""Direct inference test on real frame"""
import cv2
import numpy as np
from app.models.model_manager import model_manager
import json

# Load a real frame
frame_path = "frames/59afda6d-9159-4f75-bf2d-a0072ae2febd/frame_000000.jpg"
frame = cv2.imread(frame_path)
print(f"Frame shape: {frame.shape}")
print(f"Frame dtype: {frame.dtype}")
print(f"Frame min/max: {frame.min()}/{frame.max()}")

# Get mudra model
mudra_model = model_manager.get("mudra")
print(f"\nMudra model loaded: {mudra_model is not None}")
print(f"Mudra class names ({len(mudra_model.class_names)} total): {mudra_model.class_names[:5]}...")

# Run inference
prediction = mudra_model.predict(frame)
print(f"\nMudra prediction:")
print(json.dumps({k: v if not isinstance(v, dict) else {kk: round(vv, 6) for kk, vv in v.items()} for k, v in prediction.items()}, indent=2))

# Show top 5 probabilities
probs = prediction['probabilities']
top5 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
print(f"\nTop 5 predictions:")
for name, conf in top5:
    print(f"  {name}: {conf:.6f}")

# Also test Bhava model
print("\n" + "="*60)
bhava_model = model_manager.get("bhava")
print(f"\nBhava model loaded: {bhava_model is not None}")
print(f"Bhava class names ({len(bhava_model.class_names)} total): {bhava_model.class_names}")

# Run inference
prediction = bhava_model.predict(frame)
print(f"\nBhava prediction:")
print(json.dumps({k: v if not isinstance(v, dict) else {kk: round(vv, 6) for kk, vv in v.items()} for k, v in prediction.items()}, indent=2))

# Show top 3 probabilities
probs = prediction['probabilities']
top3 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
print(f"\nTop 3 predictions:")
for name, conf in top3:
    print(f"  {name}: {conf:.6f}")
