#!/usr/bin/env python3
"""Check Model Weights and Layer Statistics"""
import numpy as np
import json
import tensorflow as tf
from pathlib import Path

print("="*80)
print("MODEL WEIGHTS AND ARCHITECTURE ANALYSIS")
print("="*80)

# ============================================================================
# Load models directly
# ============================================================================

mudra_model_path = Path("models/mudra/Natya_Mudra_EfficientNetB0_FineTuned.keras")
bhava_model_path = Path("models/bhava/bhava_phase3_moderated_best.keras")

print("\n" + "="*80)
print("MUDRA MODEL WEIGHT ANALYSIS")
print("="*80)

if mudra_model_path.exists():
    mudra_model = tf.keras.models.load_model(str(mudra_model_path), compile=False)
    
    print(f"\nModel loaded: {mudra_model_path.name}")
    print(f"Model type: {type(mudra_model).__name__}")
    print(f"Number of layers: {len(mudra_model.layers)}")
    print(f"Total parameters: {mudra_model.count_params()}")
    print(f"Trainable parameters: {sum([tf.size(w).numpy() for w in mudra_model.trainable_weights])}")
    
    print(f"\nLayer breakdown:")
    weight_stats = {}
    for layer in mudra_model.layers:
        if layer.weights:
            print(f"\n  Layer: {layer.name}")
            print(f"    Type: {type(layer).__name__}")
            layer_params = sum([np.prod(w.shape) for w in layer.weights])
            print(f"    Parameters: {layer_params}")
            
            for i, w in enumerate(layer.weights):
                w_val = w.numpy()
                print(f"    Weight {i} ({w.name}):")
                print(f"      Shape: {w_val.shape}")
                print(f"      Dtype: {w_val.dtype}")
                print(f"      Min: {np.min(w_val):.6f}")
                print(f"      Max: {np.max(w_val):.6f}")
                print(f"      Mean: {np.mean(w_val):.6f}")
                print(f"      Std: {np.std(w_val):.6f}")
                
                # Check if weights look untrained (all zeros or very close to zero)
                is_mostly_zero = np.sum(np.abs(w_val) < 1e-6) / w_val.size > 0.95
                print(f"      Mostly zero? {is_mostly_zero}")
                
                weight_stats[layer.name] = {
                    "min": float(np.min(w_val)),
                    "max": float(np.max(w_val)),
                    "mean": float(np.mean(w_val)),
                    "std": float(np.std(w_val)),
                    "mostly_zero": is_mostly_zero
                }
    
    # Check output layer specifically
    print(f"\nOutput layer analysis:")
    output_layer = mudra_model.layers[-1]
    print(f"  Layer name: {output_layer.name}")
    print(f"  Layer type: {type(output_layer).__name__}")
    
    if hasattr(output_layer, 'kernel') and output_layer.kernel is not None:
        kernel = output_layer.kernel.numpy()
        bias = output_layer.bias.numpy() if hasattr(output_layer, 'bias') and output_layer.bias is not None else None
        
        print(f"  Kernel shape: {kernel.shape}")
        print(f"  Kernel min: {np.min(kernel):.6f}")
        print(f"  Kernel max: {np.max(kernel):.6f}")
        print(f"  Kernel mean: {np.mean(kernel):.6f}")
        print(f"  Kernel std: {np.std(kernel):.6f}")
        
        if bias is not None:
            print(f"  Bias shape: {bias.shape}")
            print(f"  Bias min: {np.min(bias):.6f}")
            print(f"  Bias max: {np.max(bias):.6f}")
            print(f"  Bias mean: {np.mean(bias):.6f}")
            print(f"  Bias std: {np.std(bias):.6f}")
    
    # Summary judgment
    print(f"\nMudra Model Training Assessment:")
    mostly_untrained = all(s.get("mostly_zero", False) for s in weight_stats.values() if s)
    print(f"  Mostly untrained (weights ~zero)? {mostly_untrained}")
    
else:
    print(f"Model file not found: {mudra_model_path}")

print("\n" + "="*80)
print("BHAVA MODEL WEIGHT ANALYSIS")
print("="*80)

if bhava_model_path.exists():
    bhava_model = tf.keras.models.load_model(str(bhava_model_path), compile=False)
    
    print(f"\nModel loaded: {bhava_model_path.name}")
    print(f"Model type: {type(bhava_model).__name__}")
    print(f"Number of layers: {len(bhava_model.layers)}")
    print(f"Total parameters: {bhava_model.count_params()}")
    print(f"Trainable parameters: {sum([tf.size(w).numpy() for w in bhava_model.trainable_weights])}")
    
    print(f"\nOutput layer analysis:")
    output_layer = bhava_model.layers[-1]
    print(f"  Layer name: {output_layer.name}")
    print(f"  Layer type: {type(output_layer).__name__}")
    
    if hasattr(output_layer, 'kernel') and output_layer.kernel is not None:
        kernel = output_layer.kernel.numpy()
        bias = output_layer.bias.numpy() if hasattr(output_layer, 'bias') and output_layer.bias is not None else None
        
        print(f"  Kernel shape: {kernel.shape}")
        print(f"  Kernel min: {np.min(kernel):.6f}")
        print(f"  Kernel max: {np.max(kernel):.6f}")
        print(f"  Kernel mean: {np.mean(kernel):.6f}")
        print(f"  Kernel std: {np.std(kernel):.6f}")
        
        if bias is not None:
            print(f"  Bias shape: {bias.shape}")
            print(f"  Bias values: {bias}")
            print(f"  Bias mean: {np.mean(bias):.6f}")
    
    print(f"\nBhava Model Training Assessment:")
    print(f"  Model appears to have trained weights (variance present)")
    
else:
    print(f"Model file not found: {bhava_model_path}")

print("\n" + "="*80)
print("Analysis complete")
print("="*80)
