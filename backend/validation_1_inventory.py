#!/usr/bin/env python3
"""COMPREHENSIVE MODEL VALIDATION - No modifications"""
import sys
import json
import numpy as np
import cv2
from pathlib import Path

# Import models
from app.models.model_manager import model_manager
from app.utils.image_utils import prepare_image

print("="*80)
print("MODEL VALIDATION REPORT")
print("="*80)

# ============================================================================
# PART 1: MODEL INVENTORY
# ============================================================================
print("\n" + "="*80)
print("PART 1: MODEL FILE INVENTORY")
print("="*80)

models_dir = Path("models")

# Mudra models
mudra_dir = models_dir / "mudra"
mudra_files = list(mudra_dir.glob("*.keras")) + list(mudra_dir.glob("*.h5"))
print(f"\nMudra model directory: {mudra_dir}")
print(f"Files found: {len(mudra_files)}")
for f in mudra_files:
    stat = f.stat()
    print(f"  - {f.name}")
    print(f"    Size: {stat.st_size / 1024 / 1024:.2f} MB")
    print(f"    Modified: {stat.st_mtime}")

# Bhava models
bhava_dir = models_dir / "bhava"
bhava_files = list(bhava_dir.glob("*.keras")) + list(bhava_dir.glob("*.h5"))
print(f"\nBhava model directory: {bhava_dir}")
print(f"Files found: {len(bhava_files)}")
for f in bhava_files:
    stat = f.stat()
    print(f"  - {f.name}")
    print(f"    Size: {stat.st_size / 1024 / 1024:.2f} MB")
    print(f"    Modified: {stat.st_mtime}")

# Pose models
pose_dir = models_dir / "pose"
pose_files = list(pose_dir.glob("*.keras")) + list(pose_dir.glob("*.h5"))
print(f"\nPose model directory: {pose_dir}")
print(f"Files found: {len(pose_files)}")
for f in pose_files:
    stat = f.stat()
    print(f"  - {f.name}")
    print(f"    Size: {stat.st_size / 1024 / 1024:.2f} MB")
    print(f"    Modified: {stat.st_mtime}")

# ============================================================================
# PART 2: CLASS NAME INVENTORY
# ============================================================================
print("\n" + "="*80)
print("PART 2: CLASS NAME INVENTORY")
print("="*80)

# Mudra classes
mudra_classes_file = mudra_dir / "mudra_class_names.json"
if mudra_classes_file.exists():
    with open(mudra_classes_file) as f:
        mudra_classes = json.load(f)
    print(f"\nMudra classes file: {mudra_classes_file.name}")
    print(f"Number of classes: {len(mudra_classes)}")
    print(f"Classes: {mudra_classes}")
    # Find Shivalinga
    if "Shivalinga" in mudra_classes:
        print(f"Shivalinga is at index: {mudra_classes.index('Shivalinga')}")
else:
    print(f"\nMudra classes file NOT FOUND: {mudra_classes_file}")
    mudra_classes = None

# Bhava classes
bhava_metadata_file = bhava_dir / "bhava_model_metadata.json"
if bhava_metadata_file.exists():
    with open(bhava_metadata_file) as f:
        bhava_metadata = json.load(f)
    bhava_classes = bhava_metadata.get("classes", [])
    print(f"\nBhava classes file: {bhava_metadata_file.name}")
    print(f"Number of classes: {len(bhava_classes)}")
    print(f"Classes: {bhava_classes}")
    if "Angry" in bhava_classes:
        print(f"Angry is at index: {bhava_classes.index('Angry')}")
else:
    print(f"\nBhava metadata file NOT FOUND: {bhava_metadata_file}")
    bhava_classes = None

# Pose classes
pose_classes_file = pose_dir / "pose_class_names.json"
if pose_classes_file.exists():
    with open(pose_classes_file) as f:
        pose_metadata = json.load(f)
    pose_classes = pose_metadata.get("class_names", [])
    print(f"\nPose classes file: {pose_classes_file.name}")
    print(f"Number of classes: {len(pose_classes)}")
    print(f"Classes: {pose_classes}")
else:
    print(f"\nPose classes file NOT FOUND: {pose_classes_file}")
    pose_classes = None

# ============================================================================
# PART 3: LOAD AND INSPECT MODELS
# ============================================================================
print("\n" + "="*80)
print("PART 3: MODEL ARCHITECTURE")
print("="*80)

import tensorflow as tf

# Load mudra model
print("\nMudra Model:")
try:
    mudra_model = model_manager.get("mudra")
    print(f"  Status: LOADED")
    print(f"  Input shape: {mudra_model.input_shape}")
    print(f"  Output shape: {mudra_model.output_shape}")
    print(f"  Classes loaded: {len(mudra_model.class_names)}")
    print(f"  Model layers: {len(mudra_model.model.layers)}")
    print(f"  Total parameters: {mudra_model.model.count_params()}")
    
    # Check output layer
    output_layer = mudra_model.model.layers[-1]
    print(f"  Output layer type: {type(output_layer).__name__}")
    print(f"  Output layer name: {output_layer.name}")
except Exception as e:
    print(f"  Status: FAILED - {e}")

# Load bhava model
print("\nBhava Model:")
try:
    bhava_model = model_manager.get("bhava")
    print(f"  Status: LOADED")
    print(f"  Input shape: {bhava_model.input_shape}")
    print(f"  Output shape: {bhava_model.output_shape}")
    print(f"  Classes loaded: {len(bhava_model.class_names)}")
    print(f"  Model layers: {len(bhava_model.model.layers)}")
    print(f"  Total parameters: {bhava_model.model.count_params()}")
    
    # Check output layer
    output_layer = bhava_model.model.layers[-1]
    print(f"  Output layer type: {type(output_layer).__name__}")
    print(f"  Output layer name: {output_layer.name}")
except Exception as e:
    print(f"  Status: FAILED - {e}")

# Load pose model
print("\nPose Model:")
try:
    pose_model = model_manager.get("pose")
    print(f"  Status: LOADED")
    print(f"  Input shape: {pose_model.input_shape}")
    print(f"  Output shape: {pose_model.output_shape}")
    print(f"  Classes loaded: {len(pose_model.class_names)}")
    print(f"  Model layers: {len(pose_model.model.layers)}")
    print(f"  Total parameters: {pose_model.model.count_params()}")
except Exception as e:
    print(f"  Status: FAILED - {e}")

print("\nDone with model validation. Check subsequent test files for prediction tests.")
