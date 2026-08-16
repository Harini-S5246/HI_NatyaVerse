"""Evidence-grounded story generation for HI-Natya Verse.

This is the interpretation layer that sits after multimodal fusion.  It is
strictly evidence-driven:

* Reads ONLY the fused result (``get_modality_result(video_id, "fusion")``).
* Builds interpretations ONLY from ``evidence.grounded`` entries.  Every
  interpretation records the exact evidence IDs that support it.
* ``evidence.detected`` is treated as model observations only and never
  transformed into a meaning claim.
* ``evidence.unresolved`` is surfaced explicitly as unresolved; its meaning
  is never invented.
* No Mudra-Bhava relationship is ever invented — the curated knowledge base
  currently contains no such links, so none are generated.
* If there is no grounded evidence, returns ``insufficient_grounded_evidence``
  with a transparent explanation instead of a hallucinated story.

The narrative is deterministic template-based (English + Tamil).  The
curated meaning values are quoted verbatim from the knowledge base in both
languages — the service never fabricates its own translations of curated
content.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.services.result_service import (
    get_modality_result,
    save_modality_result,
)

SUPPORTED_LANGUAGES = {"en", "ta"}

# Language-name aliases used by the existing frontend GET /api/story route.
LANGUAGE_ALIASES = {
    "en": "en",
    "english": "en",
    "ta": "ta",
    "tamil": "ta",
}


def _normalize_language(language: str) -> str:
    """Return the canonical language code and validate support."""
    language = (language or "en").strip().lower()
    code = LANGUAGE_ALIASES.get(language)
    if code is None or code not in SUPPORTED_LANGUAGES:
        raise AppError(
            f"Unsupported language: {language}. Supported: en, ta.",
            400,
            "UNSUPPORTED_LANGUAGE",
        )
    return code


def _build_interpretations(evidence: dict[str, list[dict]]) -> tuple[list[dict], list[str], list[str]]:
    """Build traceable interpretations from grounded evidence only.

    Returns (interpretations, supporting_evidence_ids, unresolved_evidence_ids).
    """
    interpretations: list[dict] = []
    supporting_ids: list[str] = []
    unresolved_ids: list[str] = []

    for item in evidence.get("grounded", []):
        label = item.get("label")
        detail = item.get("detail")
        evidence_id = item.get("id")
        if not label or not detail or not evidence_id:
            continue
        interpretations.append({
            "id": f"interp-{label.lower()}",
            "statement": f"The {label} gesture appears in this performance. "
                         f"In the curated knowledge base, {label} corresponds to {detail}.",
            "supporting_evidence": [evidence_id],
            "confidence": item.get("confidence"),
            "status": "evidence_supported",
        })
        supporting_ids.append(evidence_id)

    for item in evidence.get("unresolved", []):
        evidence_id = item.get("id")
        if evidence_id:
            unresolved_ids.append(evidence_id)

    return interpretations, supporting_ids, unresolved_ids


def _english_story(response: dict) -> None:
    """Fill ``title`` / ``story`` for English output from interpretations."""
    interpretations = response["interpretations"]
    if not interpretations:
        return
    response["title"] = "Evidence-Grounded Interpretation"
    lines = [
        "This interpretation is generated exclusively from evidence supported by the curated knowledge base."
    ]
    for interp in interpretations:
        lines.append(f"- {interp['statement']}")
    if response["unresolved_evidence"]:
        lines.append(
            "The following gestures were detected but could not be interpreted because "
            "they lack a verified knowledge-base entry: " + ", ".join(response["unresolved_evidence"]) + "."
        )
        lines.append("No meaning is claimed for these unresolved gestures.")
    response["story"] = "\n".join(lines)


def _tamil_story(response: dict) -> None:
    """Fill ``title`` / ``story`` for Tamil output from interpretations.

    Deterministic template scaffolding is Tamil; curated meaning values are
    quoted verbatim (never fabricated translations).
    """
    interpretations = response["interpretations"]
    if not interpretations:
        return
    response["title"] = "சான்று அடிப்படையிலான விளக்கம்"
    lines = [
        "இந்த விளக்கம், அறிவுத் தளத்தால் ஆதரிக்கப்படும் சான்றுகளை மட்டுமே அடிப்படையாகக் கொண்டது."
    ]
    # Statements carry the curated English meaning verbatim; Tamil scaffolding
    # frames them without translating or altering the curated content.
    for interp in interpretations:
        lines.append(f"- {interp['statement']}")
    if response["unresolved_evidence"]:
        lines.append(
            "பின்வரும் முத்திரைகள் கண்டறியப்பட்டன, ஆனால் சரிபார்க்கப்பட்ட அறிவுத் தளப் "
            "பதிவு இல்லாததால் விளக்கப்படவில்லை: " + ", ".join(response["unresolved_evidence"]) + "."
        )
        lines.append("இந்தத் தீர்க்கப்படாத முத்திரைகளுக்கு எந்த அர்த்தமும் கூறப்படவில்லை.")
    response["story"] = "\n".join(lines)


def generate_story(video_id: str, language: str = "en") -> dict:
    """Generate an evidence-grounded story for one fused video result."""
    code = _normalize_language(language)

    try:
        fusion = get_modality_result(video_id, "fusion")
    except AppError as exc:
        if exc.code == "MODALITY_RESULT_NOT_FOUND":
            raise AppError(
                "Fusion result was not found for this video. Run the fusion analysis first.",
                404,
                "FUSION_RESULT_REQUIRED",
            ) from exc
        raise

    evidence = fusion.get("evidence", {})
    interpretations, supporting_ids, unresolved_ids = _build_interpretations(evidence)

    response: dict[str, Any] = {
        "analysis_id": video_id,
        "status": "completed" if interpretations else "insufficient_grounded_evidence",
        "language": code,
        "title": None,
        "story": None,
        "interpretations": interpretations,
        "supporting_evidence": supporting_ids,
        "unresolved_evidence": unresolved_ids,
        "message": None,
    }

    if interpretations:
        if code == "ta":
            _tamil_story(response)
        else:
            _english_story(response)
    else:
        response["message"] = (
            "No grounded evidence was found in the curated knowledge base. "
            "The story cannot be generated because every detected gesture is either "
            "unresolved or model-detected only. No interpretation is fabricated."
            if code == "en"
            else "சரிபார்க்கப்பட்ட அறிவுத் தளத்தில் எந்தச் சான்றும் கிடைக்கவில்லை. "
                 "ஒவ்வொரு கண்டறியப்பட்ட முத்திரையும் தீர்க்கப்படாததாகவோ அல்லது மாதிரி-கண்டறிதல் "
                 "மட்டுமாகவோ இருப்பதால், கதையை உருவாக்க முடியாது. எந்த விளக்கமும் கற்பனையாக "
                 "உருவாக்கப்படவில்லை."
        )

    # Persist the story as its own modality entry (does NOT overwrite the
    # top-level analysis JSON that the existing GET endpoints read).
    save_modality_result(video_id, "story", response)
    return response
