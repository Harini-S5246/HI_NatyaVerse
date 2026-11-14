#!/usr/bin/env python3
"""Test mudra model on multiple frames to see if it varies or always predicts same class"""
import cv2
from app.models.model_manager import model_manager

mudra_model = model_manager.get("mudra")
print(f"Mudra model loaded: {mudra_model is not None}\n")

# Test frames 0, 10, 50, 100, 150, 200 from video 1
frames_to_test = [0, 10, 50, 100, 150, 200]
video_id = "59afda6d-9159-4f75-bf2d-a0072ae2febd"

predictions = {}
for frame_num in frames_to_test:
    frame_path = f"frames/{video_id}/frame_{frame_num:06d}.jpg"
    try:
        frame = cv2.imread(frame_path)
        if frame is None:
            print(f"Frame {frame_num}: NOT FOUND")
            continue
        
        prediction = mudra_model.predict(frame)
        label = prediction['label']
        confidence = prediction['confidence']
        predictions[frame_num] = (label, confidence)
        
        # Get argmax across all classes
        probs = prediction['probabilities']
        max_class = max(probs.items(), key=lambda x: x[1])
        
        print(f"Frame {frame_num:06d}: {label:15s} ({confidence:.6f}) | Max class: {max_class[0]:15s} ({max_class[1]:.6f})")
    except Exception as e:
        print(f"Frame {frame_num}: ERROR - {e}")

print("\n" + "="*80)
print("SUMMARY:")
labels_found = set(p[0] for p in predictions.values())
print(f"Unique labels across {len(predictions)} frames: {labels_found}")
print(f"All same label? {len(labels_found) == 1}")

# Also test a frame from a completely different video
print("\n" + "="*80)
print("Testing on different video:")
video_id2 = "0b1c2d39-a7c8-4d97-aff2-b08e166126a4"
frame_path = f"frames/{video_id2}/frame_000000.jpg"
frame = cv2.imread(frame_path)
prediction = mudra_model.predict(frame)
print(f"Video 2, Frame 0: {prediction['label']} ({prediction['confidence']:.6f})")
