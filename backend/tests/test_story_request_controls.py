"""Focused regression checks for request consumption controls."""
from __future__ import annotations

from pathlib import Path
import re

from app.services.llm.base import StructuredGenerationRequest
from app.services.llm.gemini_provider import GeminiProvider


ROOT = Path(__file__).resolve().parents[2]


def test_gemini_429_extracts_retry_delay_without_exposing_raw_provider_error(monkeypatch):
    provider = GeminiProvider()

    class _Client:
        def generate_content(self, *_args, **_kwargs):
            raise RuntimeError("429 ResourceExhausted: retry_delay: 52s quota_limit: 20")

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))

    assert result.error_code == "GEMINI_RATE_LIMITED"
    assert result.retry_after_seconds == 52


def test_story_pages_do_not_post_generation_from_effects_or_analysis_pipeline():
    story = (ROOT / "frontend" / "src" / "pages" / "Story.tsx").read_text(encoding="utf-8")
    analyze = (ROOT / "frontend" / "src" / "pages" / "Analyze.tsx").read_text(encoding="utf-8")
    demonstration = (ROOT / "frontend" / "src" / "pages" / "DemonstrationStory.tsx").read_text(encoding="utf-8")

    assert "void load()" in story  # Page view performs the cached GET only.
    effect = re.search(r"useEffect\(\(\) => \{(.*?)\}, \[analysisId, language\]\)", story, re.DOTALL)
    assert effect is not None
    assert "generate" not in effect.group(1)
    assert "generateStory" not in analyze
    assert "useEffect" not in demonstration
    assert "Generate Demonstration Story" in demonstration


def test_story_generation_button_has_a_client_side_single_flight_guard():
    story = (ROOT / "frontend" / "src" / "pages" / "Story.tsx").read_text(encoding="utf-8")
    assert "const generating = useRef(false)" in story
    assert "if (!analysisId || generating.current) return" in story
    assert "generating.current = false" in story
