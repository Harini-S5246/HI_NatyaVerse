#!/usr/bin/env python3
"""Test Bhava Model on Various Inputs"""
import numpy as np
import cv2
import json
from pathlib import Path
from app.models.model_manager import model_manager

print("="*80)
print("BHAVA MODEL TESTING")
print("="*80)

bhava_model = model_manager.get("bhava")

# Test 1: Synthetic inputs
print("\n" + "="*80)
print("SYNTHETIC INPUT TESTS")
print("="*80)

synthetic_tests = {
    "black_image": np.zeros((224, 224, 3), dtype=np.uint8),
    "white_image": np.ones((224, 224, 3), dtype=np.uint8) * 255,
    "random_noise_seed42": np.random.RandomState(42).randint(0, 256, (224, 224, 3), dtype=np.uint8),
    "random_noise_seed99": np.random.RandomState(99).randint(0, 256, (224, 224, 3), dtype=np.uint8),
}

synthetic_results = {}

for name, img in synthetic_tests.items():
    pred = bhava_model.predict(img)
    label = pred['label']
    confidence = pred['confidence']
    probs = pred['probabilities']
    
    top5 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
    
    synthetic_results[name] = {
        "predicted_label": label,
        "confidence": confidence,
        "all_classes": {k: round(v, 6) for k, v in probs.items()}
    }
    
    print(f"\n{name}:")
    print(f"  Predicted: {label} ({confidence:.6f})")
    print(f"  All classes: {', '.join([f'{k}({v:.6f})' for k, v in sorted(probs.items(), key=lambda x: x[1], reverse=True)])}")

# Test 2: Real frames
print("\n" + "="*80)
print("REAL VIDEO FRAMES TEST")
print("="*80)

video_id = "59afda6d-9159-4f75-bf2d-a0072ae2febd"
frame_dir = Path(f"frames/{video_id}")

if frame_dir.exists():
    frame_files = sorted(frame_dir.glob("frame_*.jpg"))
    print(f"\nTotal frames in video: {len(frame_files)}")
    
    # Sample specific frames
    test_frame_indices = [0, 10, 50, 100, 150, 200]
    real_results = {}
    
    predictions_distribution = {}
    
    for idx in test_frame_indices:
        frame_path = frame_dir / f"frame_{idx:06d}.jpg"
        if frame_path.exists():
            frame = cv2.imread(str(frame_path))
            pred = bhava_model.predict(frame)
            label = pred['label']
            confidence = pred['confidence']
            probs = pred['probabilities']
            
            real_results[f"frame_{idx}"] = {
                "predicted_label": label,
                "confidence": confidence,
                "all_classes": {k: round(v, 6) for k, v in probs.items()}
            }
            
            print(f"\nFrame {idx:06d}: {label} ({confidence:.6f})")

    # Analyze ALL frames
    print("\n" + "-"*80)
    print("DISTRIBUTION ACROSS ALL FRAMES")
    print("-"*80)
    
    all_predictions = []
    
    for i, frame_file in enumerate(frame_files):
        try:
            frame = cv2.imread(str(frame_file))
            if frame is None:
                continue
            pred = bhava_model.predict(frame)
            label = pred['label']
            confidence = pred['confidence']
            all_predictions.append((label, confidence))
            
            if label not in predictions_distribution:
                predictions_distribution[label] = {"count": 0, "confidences": []}
            predictions_distribution[label]["count"] += 1
            predictions_distribution[label]["confidences"].append(confidence)
        except Exception as e:
            print(f"Error processing frame {i}: {e}")
            continue
    
    print(f"\nTotal frames analyzed: {len(all_predictions)}")
    print(f"Unique classes predicted: {len(predictions_distribution)}")
    print(f"\nPrediction distribution:")
    
    for label in sorted(predictions_distribution.keys(), key=lambda k: predictions_distribution[k]["count"], reverse=True):
        data = predictions_distribution[label]
        confs = data["confidences"]
        print(f"  {label}:")
        print(f"    Count: {data['count']}")
        print(f"    Mean confidence: {np.mean(confs):.6f}")
        print(f"    Min confidence: {np.min(confs):.6f}")
        print(f"    Max confidence: {np.max(confs):.6f}")
        print(f"    Std Dev: {np.std(confs):.6f}")
else:
    print(f"Frame directory not found: {frame_dir}")

# Store results
print("\n" + "="*80)
print("SAVING RESULTS")
print("="*80)

results = {
    "model": "bhava",
    "metadata": {
        "model_accuracy": 0.5783,
        "macro_f1": 0.5372,
        "weighted_f1": 0.567
    },
    "synthetic_tests": synthetic_results,
    "real_frame_samples": real_results if 'real_results' in locals() else {},
    "distribution": {k: {
        "count": v["count"],
        "mean_confidence": float(np.mean(v["confidences"])),
        "min_confidence": float(np.min(v["confidences"])),
        "max_confidence": float(np.max(v["confidences"])),
        "std_dev": float(np.std(v["confidences"]))
    } for k, v in predictions_distribution.items()} if 'predictions_distribution' in locals() else {}
}

with open("validation_bhava_predictions.json", "w") as f:
    json.dump(results, f, indent=2)

print("Results saved to: validation_bhava_predictions.json")
