#!/usr/bin/env python3
"""Test mudra model with synthetic inputs"""
import numpy as np
from app.models.model_manager import model_manager

mudra = model_manager.get('mudra')
print(f"Mudra model loaded: {mudra is not None}\n")

# Test 1: All zeros
zeros = np.zeros((224, 224, 3), dtype=np.uint8)
from app.utils.image_utils import prepare_image
input_zeros = prepare_image(zeros)
output = mudra.model.predict(input_zeros, verbose=0)
scores = np.asarray(output)[0]
print(f"Test 1 - All zeros (black image):")
print(f"  Argmax: {np.argmax(scores)} ({mudra.class_names[np.argmax(scores)]})")
print(f"  Max value: {np.max(scores):.6f}")
print(f"  Shivalinga (index 38): {scores[38]:.6f}")

# Test 2: All ones (white)
ones = np.ones((224, 224, 3), dtype=np.uint8) * 255
input_ones = prepare_image(ones)
output = mudra.model.predict(input_ones, verbose=0)
scores = np.asarray(output)[0]
print(f"\nTest 2 - All ones (white image):")
print(f"  Argmax: {np.argmax(scores)} ({mudra.class_names[np.argmax(scores)]})")
print(f"  Max value: {np.max(scores):.6f}")
print(f"  Shivalinga (index 38): {scores[38]:.6f}")

# Test 3: Random noise
np.random.seed(42)
noise = np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8)
input_noise = prepare_image(noise)
output = mudra.model.predict(input_noise, verbose=0)
scores = np.asarray(output)[0]
print(f"\nTest 3 - Random noise:")
print(f"  Argmax: {np.argmax(scores)} ({mudra.class_names[np.argmax(scores)]})")
print(f"  Max value: {np.max(scores):.6f}")
print(f"  Shivalinga (index 38): {scores[38]:.6f}")

print(f"\nAll outputs similar? This suggests the model might not be properly trained.")
print(f"If the model always outputs uniform probabilities (~1/48 ≈ 0.021), something is wrong.")
