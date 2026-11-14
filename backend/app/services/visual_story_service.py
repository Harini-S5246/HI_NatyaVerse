"""Visual story generation from uploaded performance frames.

This module provides the AI Visual Story path for real uploaded videos.
It does not depend on verified narrative evidence or human review.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.errors import AppError
from app.services.llm import get_provider
from app.services.llm.base import LLMProvider, StructuredGenerationRequest
from app.services.result_service import get_modality_result, save_modality_result, modality_result_path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
_MAX_FRAMES = 18
_MIN_FRAMES = 8


def _load_frame_manifest(analysis_id: str) -> dict[str, Any] | None:
    """Load the frame extraction manifest for an analysis."""
    manifest_path = settings.frame_output_dir / analysis_id / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        import json
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_fusion(analysis_id: str) -> dict[str, Any] | None:
    """Load fusion result for timeline and evidence."""
    try:
        return get_modality_result(analysis_id, "fusion")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            return None
        raise


def _select_representative_frames(
    manifest: dict[str, Any],
    fusion: dict[str, Any] | None,
    max_frames: int = _MAX_FRAMES,
) -> list[dict[str, Any]]:
    """Select chronologically distributed representative frames.
    
    Prioritizes frames around Mudra/Bhava transitions when fusion is available.
    """
    frames = manifest.get("frames", [])
    if not frames:
        return []
    
    total = len(frames)
    if total <= max_frames:
        return frames
    
    selected: list[dict[str, Any]] = []
    
    # Always include first and last
    selected.append(frames[0])
    selected.append(frames[-1])
    
    # If we have fusion timeline, find transition points
    transition_indices: set[int] = set()
    if fusion and fusion.get("timeline"):
        timeline = fusion["timeline"]
        for i, entry in enumerate(timeline):
            if i == 0:
                continue
            prev = timeline[i - 1]
            # Detect Mudra or Bhava changes
            if (entry.get("mudra") != prev.get("mudra") or
                entry.get("bhava") != prev.get("bhava")):
                # Find closest frame index to this timestamp
                ts = entry.get("start_time", 0)
                idx = min(range(total), key=lambda j: abs(frames[j]["timestamp"] - ts))
                transition_indices.add(idx)
    
    # Add transition frames (up to remaining budget)
    remaining = max_frames - len(selected)
    for idx in sorted(transition_indices):
        if remaining <= 0:
            break
        if idx not in (0, total - 1) and frames[idx] not in selected:
            selected.append(frames[idx])
            remaining -= 1
    
    # Fill remaining with evenly distributed frames
    if remaining > 0:
        step = total / (remaining + 1)
        for i in range(1, remaining + 1):
            idx = int(round(i * step))
            if idx >= total - 1:
                idx = total - 2
            if idx > 0 and frames[idx] not in selected:
                selected.append(frames[idx])
    
    # Sort by timestamp and deduplicate
    seen_ts: set[float] = set()
    unique: list[dict[str, Any]] = []
    for f in sorted(selected, key=lambda x: x["timestamp"]):
        ts = f["timestamp"]
        if ts not in seen_ts:
            seen_ts.add(ts)
            unique.append(f)
    
    return unique[:max_frames]


def _build_visual_prompt(
    analysis_id: str,
    selected_frames: list[dict[str, Any]],
    fusion: dict[str, Any] | None,
    language: str = "en",
) -> str:
    """Build the visual story prompt with frame context."""
    language_names = {
        "en": "English", "ta": "Tamil", "hi": "Hindi", "ml": "Malayalam",
    }
    lang_name = language_names.get(language, "English")
    
    # Prepare timeline summary from fusion
    timeline_summary = ""
    grounded_mudras: list[str] = []
    unresolved_mudras: list[str] = []
    expression_observations: list[dict[str, Any]] = []
    
    if fusion:
        summary = fusion.get("summary", {})
        evidence = fusion.get("evidence", {})
        
        if summary.get("dominant_mudra"):
            timeline_summary += f"Dominant Mudra: {summary['dominant_mudra']}. "
        if summary.get("dominant_bhava"):
            timeline_summary += f"Most common predicted emotion label: {summary['dominant_bhava']}. "
        if summary.get("frame_count"):
            timeline_summary += f"Total frames analyzed: {summary['frame_count']}. "
        
        for item in evidence.get("grounded", []):
            if (
                item.get("verification_status") in {"verified", "partially_verified"}
                and item.get("knowledge_status") == item.get("verification_status")
                and isinstance(item.get("claim_id"), str)
                and item["claim_id"].strip()
                and isinstance(item.get("source_references"), list)
                and item["source_references"]
                and all(isinstance(reference, str) and reference.strip() for reference in item["source_references"])
                and isinstance(item.get("uncertainty_notes"), list)
                and all(isinstance(note, str) for note in item["uncertainty_notes"])
            ):
                grounded_mudras.append(
                    f"{item['label']} ({item.get('detail', 'meaning available')}; "
                    f"{item['verification_status']}; claim {item['claim_id']}; "
                    f"sources: {', '.join(item['source_references'])}; "
                    f"uncertainty: {'; '.join(item['uncertainty_notes']) or 'none recorded'})"
                )
        for item in evidence.get("unresolved", []):
            unresolved_mudras.append(item["label"])
        
        # Preserve predicted emotion labels as generic observations.
        seen_bhava: set[str] = set()
        for entry in fusion.get("timeline", []):
            bhava = entry.get("bhava")
            if bhava and bhava not in seen_bhava:
                seen_bhava.add(bhava)
                expression_observations.append({
                    "bhava": bhava,
                    "start_time": entry.get("start_time"),
                    "end_time": entry.get("end_time"),
                })
    
    frame_info = "\n".join(
        f"  Frame {i}: timestamp={f['timestamp']:.1f}s, filename={f['filename']}"
        for i, f in enumerate(selected_frames)
    )
    
    return f"""You are an AI visual interpreter for HI-Natya Verse analyzing a Bharatanatyam performance.

You are given a sequence of timestamped video frames from an uploaded performance, along with supporting analysis evidence from Mudra and a generic facial-expression classifier.

Your task: Write a natural, chronological Bharatanatyam performance narrative based on what you see in the frames and what the analysis evidence tells you.

============================================================
VISUAL EVIDENCE
============================================================
Performance ID: {analysis_id}
Selected frames ({len(selected_frames)} frames):
{frame_info}

Performance duration: {selected_frames[-1]['timestamp']:.1f}s (from first to last selected frame)

============================================================
ANALYSIS EVIDENCE (supporting, not primary)
============================================================
{timeline_summary}

Mudra knowledge-base meanings (with verification status and provenance):
{chr(10).join(f"  - {m}" for m in grounded_mudras) if grounded_mudras else "  (none)"}

Unresolved Mudras (no reliable knowledge-base meaning available):
{chr(10).join(f"  - {m}" for m in unresolved_mudras) if unresolved_mudras else "  (none)"}

Predicted emotion-label observations (not classical Bhava or Rasa classifications):
{chr(10).join(f"  - {b['bhava']} at {b['start_time']:.1f}-{b['end_time']:.1f}s" for b in expression_observations) if expression_observations else "  (no facial-expression observations)"}

============================================================
GUIDELINES
============================================================
1. BASE YOUR NARRATIVE PRIMARILY ON THE VISUAL FRAMES. The analysis evidence supports but does not replace what you see.

2. Write in chronological order following the frame timestamps.

3. Describe what you observe: hand gestures, body posture, movement quality, facial expression, spatial positioning, and how these change over time.

4. When a source-backed Mudra meaning is available, describe it only with its supplied verification status. Do NOT infer a Mudra–emotion relationship.

5. For unresolved Mudras, describe the visual shape of the gesture without assigning invented meanings.

6. Describe predicted emotion labels only as generic facial-expression observations, never as classical Bhava or Rasa recognition; do NOT invent causes.

7. You MAY identify specific characters (Krishna, Radha, Shiva, Devi) or locations (forest, temple) ONLY IF the visual evidence in the frames clearly supports it (costume, iconography, distinctive attributes). If uncertain, describe the observable choreography instead.

8. NEVER invent: dialogue, lyrics, song meaning, relationships, intentions, off-screen events, or causal narratives unsupported by the visual evidence.

9. If the visual evidence is insufficient for a specific interpretation, acknowledge it: "The visual sequence does not provide enough evidence to identify a specific character or mythological episode." Then continue with a useful performance narrative based on observable movement.

10. Write 3-5 paragraphs. Use natural, human-readable language. Avoid technical jargon, confidence scores, or JSON field names.

============================================================
OUTPUT FORMAT
============================================================
Return a JSON object with exactly these fields:
{{
  "title": "A natural title for the performance",
  "narrative": "The complete story text (3-5 paragraphs)",
  "sections": {{
    "opening": "What the performance establishes visually at the beginning",
    "development": "How the sequence develops through the middle",
    "emotional_progression": "Observed Bhava/expression changes",
    "gesture_progression": "Meaningful Mudra/gesture progression",
    "closing": "How the visual sequence concludes"
  }},
  "evidence_basis": "Brief description of frames and analysis used",
  "limitations": "This is an AI visual interpretation based on the uploaded performance frames and analysis evidence. It is not independently verified choreography or mythology."
}}

Language: {lang_name}

Generate the visual story now."""