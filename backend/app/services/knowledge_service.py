"""Evidence grounding for HI-Natya Verse.

This module is the anti-hallucination backbone of the project:

* ``ground_mudra`` looks a detected label up in the curated knowledge base.
  A mudra is grounded ONLY when the knowledge base has a ``curated`` entry
  for it.  A label that exists in the base but is ``pending_research`` stays
  unresolved.
* ``build_evidence`` reassembles a stored analysis result into the four
  part evidence object the frontend contract expects:

    - ``grounded``   -> supported by curated knowledge
    - ``detected``   -> reported by a model (bhava / pose / audio)
    - ``unresolved`` -> reported by a model but lacking curated knowledge
    - ``interpreted``-> derived from multiple evidence signals
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from app.config import settings
from app.utils.json_utils import load_json

logger = logging.getLogger(__name__)

# Labels with only namesake meaning are considered curated now; this list may
# grow as more research-verified entries are added to the knowledge file.
CURATED_STATUS = "curated"


class KnowledgeService:
    """Lazy, thread-safe access to the curated Bharatanatyam knowledge base."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, dict[str, Any]] | None = None
        self._load_error: str | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load (once) and return the raw knowledge entries."""
        if self._entries is not None:
            return self._entries

        with self._lock:
            if self._entries is not None:
                return self._entries

            path = settings.mudra_knowledge_path
            if not path or not path.is_file():
                self._load_error = f"Mudra knowledge base is missing: {path}"
                logger.error(self._load_error)
                return {}

            try:
                raw = load_json(path)
            except Exception as exc:  # noqa: BLE001 - surfaced as load_error
                self._load_error = f"Mudra knowledge base could not be read: {exc}"
                logger.exception(self._load_error)
                return {}

            if not isinstance(raw, dict):
                self._load_error = "Mudra knowledge base must be a JSON object."
                logger.error(self._load_error)
                return {}

            # Strip metadata so only per-mudra entries are kept.
            entries = {
                label: entry
                for label, entry in raw.items()
                if label != "_metadata" and isinstance(entry, dict)
            }
            self._entries = entries
            return entries

    # ------------------------------------------------------------------
    # Grounding lookups
    # ------------------------------------------------------------------

    def load_error(self) -> str | None:
        """Return the last load error, if any."""
        self._load()
        return self._load_error

    def is_available(self) -> bool:
        return self._load_error is None and bool(self._load())

    def ground_mudra(self, label: str) -> dict[str, Any] | None:
        """Return grounded knowledge for a mudra label, or None when unresolved.

        A label is grounded only when its entry exists AND has status
        ``curated``.  Labels that are present but ``pending_research`` or
        labels missing entirely remain explicitly unresolved.
        """
        entries = self._load()
        if self._load_error is not None:
            return None

        entry = entries.get(label)
        if not entry:
            return None
        if entry.get("status") != CURATED_STATUS:
            return None

        meaning = entry.get("meaning")
        if not isinstance(meaning, str) or not meaning.strip():
            return None

        return {
            "meaning": meaning.strip(),
            "usage": [item for item in entry.get("usage", []) if isinstance(item, str)],
            "associated_bhava": [
                item for item in entry.get("associated_bhava", []) if isinstance(item, str)
            ],
            "source": entry.get("source") if isinstance(entry.get("source"), str) else None,
            "status": CURATED_STATUS,
        }

    # ------------------------------------------------------------------
    # Evidence assembly
    # ------------------------------------------------------------------

    def build_evidence(self, result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Build the four-part evidence object for one stored analysis result.

        The result is expected to have the shape produced by
        ``multimodal_service.build_result`` or ``mudra_service`` (which both
        carry ``mudra.detections``, ``bhava.dominant_emotion`` and
        ``pose.primary_pose``).

        Rules:
        * A mudra detection is ``grounded`` only when the curated knowledge
          base has a ``curated`` entry for its label.
        * A mudra detection without curated knowledge is ``unresolved``.
        * Bhava / pose detections are model outputs => ``detected``.
        * No claim is ever invented here.
        """
        grounded: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        detected: list[dict[str, Any]] = []
        interpreted: list[dict[str, Any]] = []

        # --- Mudra detections -------------------------------------------
        seen_labels: set[str] = set()
        for item in result.get("mudra", {}).get("detections", []):
            label = item.get("name")
            if not isinstance(label, str) or not label:
                continue
            # Collapse duplicate / consecutive events for the same label so
            # the evidence panel shows one item per distinct mudra.
            if label in seen_labels:
                continue
            seen_labels.add(label)

            knowledge = self.ground_mudra(label)
            base = {
                "id": f"mudra-{label}",
                "label": label,
                "confidence": item.get("confidence"),
            }
            if knowledge:
                grounded.append(
                    {
                        **base,
                        "category": "grounded",
                        "detail": knowledge["meaning"],
                        "usage": knowledge["usage"],
                        "associated_bhava": knowledge["associated_bhava"],
                        "source": knowledge["source"],
                    }
                )
            else:
                unresolved.append(
                    {
                        **base,
                        "category": "unresolved",
                        "detail": "Meaning unavailable in current knowledge base",
                    }
                )

        # --- Bhava -------------------------------------------------------
        dominant = result.get("bhava", {}).get("dominant_emotion")
        if isinstance(dominant, str) and dominant:
            detected.append(
                {
                    "id": "bhava-dominant",
                    "label": f"{dominant} bhava detected",
                    "category": "detected",
                    "confidence": result.get("bhava", {}).get("confidence")
                    or result.get("bhava", {}).get("bhava_confidence"),
                }
            )

        # --- Pose --------------------------------------------------------
        primary_pose = result.get("pose", {}).get("primary_pose")
        if isinstance(primary_pose, str) and primary_pose:
            detected.append(
                {
                    "id": "pose-primary",
                    "label": f"{primary_pose} pose detected",
                    "category": "detected",
                    "confidence": result.get("pose", {}).get("confidence")
                    or result.get("pose", {}).get("pose_confidence"),
                }
            )

        return {
            "grounded": grounded,
            "detected": detected,
            "unresolved": unresolved,
            "interpreted": interpreted,
        }


# Module-level singleton so FastAPI endpoints and services share one cache.
knowledge_service = KnowledgeService()


def ground_mudra(label: str) -> dict[str, Any] | None:
    return knowledge_service.ground_mudra(label)


def build_evidence(result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return knowledge_service.build_evidence(result)


def load_error() -> str | None:
    return knowledge_service.load_error()