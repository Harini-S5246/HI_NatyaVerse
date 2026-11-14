import logging
from fastapi import APIRouter
import numpy as np

from app.models.model_manager import model_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Health"])

@router.get("/health")
def health() -> dict:
    return {"status": "ok", "models": model_manager.status()}

@router.get("/health/models")
def model_health() -> dict:
    """Load each configured model once, then report its runtime metadata."""
    return model_manager.status()


@router.get("/health/models/diagnostic")
def model_diagnostic() -> dict:
    """
    Perform detailed diagnostic checks on loaded models.
    
    Tests for:
    - Model availability
    - Input-invariant predictions (suspicious pattern)
    - Output ranges
    
    Returns diagnostic results with warnings if issues detected.
    """
    status = {}
    
    for model_name in ("mudra", "bhava", "pose"):
        try:
            model = model_manager.get(model_name)
            diagnostics = _run_model_diagnostic(model, model_name)
            
            status[model_name] = {
                "status": "loaded",
                "error": None,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            status[model_name] = {
                "status": "failed",
                "error": str(exc),
                "diagnostics": {"status": "error", "reason": str(exc)},
            }
    
    # Overall status
    all_loaded = all(s["status"] == "loaded" for s in status.values())
    any_suspicious = any(
        s.get("diagnostics", {}).get("status") == "suspicious" 
        for s in status.values()
    )
    
    return {
        "all_models_available": all_loaded,
        "any_models_suspicious": any_suspicious,
        "models": status,
    }


def _run_model_diagnostic(model, model_name: str) -> dict:
    """
    Run diagnostic tests on a model.
    
    Creates synthetic inputs (black, white, noise) and checks if the
    model produces nearly identical outputs regardless of input.
    
    Input-invariant predictions suggest the model is not learning
    discriminative features and may be producing fake/biased outputs.
    """
    try:
        # Create different test inputs
        black = np.zeros((224, 224, 3), dtype=np.float32)
        white = np.ones((224, 224, 3), dtype=np.float32)
        noise = np.random.rand(224, 224, 3).astype(np.float32)
        
        # Add batch dimension
        black_batch = np.expand_dims(black, axis=0)
        white_batch = np.expand_dims(white, axis=0)
        noise_batch = np.expand_dims(noise, axis=0)
        
        # Run predictions
        pred_black = model.predict(black_batch, verbose=0)
        pred_white = model.predict(white_batch, verbose=0)
        pred_noise = model.predict(noise_batch, verbose=0)
        
        # Calculate variation (max difference across all predictions)
        diff_bw = np.max(np.abs(pred_black - pred_white))
        diff_bn = np.max(np.abs(pred_black - pred_noise))
        diff_wn = np.max(np.abs(pred_white - pred_noise))
        
        max_diff = max(diff_bw, diff_bn, diff_wn)
        mean_diff = (diff_bw + diff_bn + diff_wn) / 3.0
        
        # Get top prediction for each
        top_black = np.argmax(pred_black[0])
        top_white = np.argmax(pred_white[0])
        top_noise = np.argmax(pred_noise[0])
        
        same_top = (top_black == top_white == top_noise)
        
        # Determine health status
        if max_diff < 0.01 or (same_top and mean_diff < 0.02):
            # Very low prediction variation suggests input-invariant output
            return {
                "status": "suspicious",
                "reason": "Model produces nearly identical outputs for different inputs",
                "details": {
                    "max_output_difference": float(max_diff),
                    "mean_output_difference": float(mean_diff),
                    "same_top_prediction_across_inputs": same_top,
                    "top_predictions": {
                        "black_image": int(top_black),
                        "white_image": int(top_white),
                        "random_noise": int(top_noise),
                    },
                },
                "warning": f"Model may not be learning discriminative features. Check training data and model weights.",
            }
        elif max_diff < 0.1:
            # Low variation but not extreme
            return {
                "status": "degraded",
                "reason": "Model shows low output variation across inputs",
                "details": {
                    "max_output_difference": float(max_diff),
                    "mean_output_difference": float(mean_diff),
                    "same_top_prediction_across_inputs": same_top,
                },
                "warning": "Consider validating model training and performance metrics",
            }
        else:
            # Normal variation
            return {
                "status": "normal",
                "reason": "Model produces appropriately varying outputs",
                "details": {
                    "max_output_difference": float(max_diff),
                    "mean_output_difference": float(mean_diff),
                    "same_top_prediction_across_inputs": same_top,
                },
            }
    except Exception as exc:
        logger.warning("Model diagnostic failed for %s: %s", model_name, exc)
        return {
            "status": "error",
            "reason": f"Diagnostic could not be performed: {exc}",
        }

