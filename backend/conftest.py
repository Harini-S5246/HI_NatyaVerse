"""Global test safety: the normal suite never contacts a live LLM provider."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def block_live_gemini_requests(monkeypatch):
    """Fail closed if an unmocked test reaches the Gemini transport.

    Tests that exercise the adapter install an instance-level fake client, so
    this guard remains compatible with deterministic provider tests.
    """
    from app.services.llm.gemini_provider import GeminiProvider

    class _BlockedClient:
        def generate_content(self, *_args, **_kwargs):
            raise AssertionError("Live Gemini requests are forbidden in the normal pytest suite.")

    monkeypatch.setattr(GeminiProvider, "_get_client", lambda _self: _BlockedClient())
