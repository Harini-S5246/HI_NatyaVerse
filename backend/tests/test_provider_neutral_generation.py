"""Provider-neutral live narration tests; no network services are used."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import narrative_generation_service
from app.services import story_integration_service
from app.core.errors import AppError
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest
from app.services.llm.gemini_provider import GeminiProvider, _rate_limit_details
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.performance_interpretation_service import build_performance_interpretation


FIXTURE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "narrative" / "narrative_evidence.example.json"


def _package():
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["source_type"] = "expert_annotation"
    record["production_eligible"] = True
    return build_performance_interpretation("provider-test", record)


class _StubProvider(LLMProvider):
    def __init__(self, name, result):
        self.name, self._model_name, self._result = name, f"{name}-model", result
        self.requests = []

    def is_available(self):
        return True

    @property
    def model(self):
        return self._model_name

    def generate(self, request):
        self.requests.append(request)
        return self._result


def _valid_output(package):
    event = package["events"][0]
    return json.dumps({"title": "Verified sequence", "narrative": event["statement"], "used_event_ids": [event["event_id"]]})


def test_configured_provider_receives_one_common_request_and_metadata(monkeypatch):
    package = _package()
    provider = _StubProvider("gemini", LLMResult(_valid_output(package), "gemini", "gemini-model"))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini"))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: provider)
    result = narrative_generation_service.generate_narrative(package)
    assert result["status"] == "generated"
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-model"
    assert len(provider.requests) == 1
    assert isinstance(provider.requests[0], StructuredGenerationRequest)
    assert "EVIDENCE:" in provider.requests[0].prompt


@pytest.mark.parametrize("provider_class, expected", [(GeminiProvider, "GEMINI_API_KEY"), (OpenAIProvider, "OPENAI_API_KEY")])
def test_missing_cloud_credentials_are_clear_and_never_fall_back(monkeypatch, provider_class, expected):
    provider = provider_class()
    monkeypatch.setattr(provider, "is_available", lambda: False)
    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))
    assert result.text == ""
    assert expected in (result.error or "")
    assert result.provider == provider.name


def test_configured_unavailable_provider_is_blocked_without_fallback(monkeypatch):
    package = _package()
    provider = _StubProvider("openai", LLMResult("", "openai", "openai-model", error="OPENAI_API_KEY is not configured"))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="openai"))
    requested = []

    def get_configured_provider(name):
        requested.append(name)
        assert name == "openai"
        return provider

    monkeypatch.setattr(narrative_generation_service, "get_provider", get_configured_provider)
    result = narrative_generation_service.generate_narrative(package)
    assert result["status"] == "blocked"
    assert result["provider"] == "openai"
    assert "OPENAI_API_KEY" in result["message"]
    assert len(provider.requests) == 1
    assert requested == ["openai"]


def test_gemini_missing_api_key_is_clear_and_never_falls_back(monkeypatch):
    package = _package()
    provider = _StubProvider("gemini", LLMResult("", "gemini", "configured-gemini-model", error="GEMINI_API_KEY is not configured or the SDK is not installed."))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini"))
    requested = []

    def get_configured_provider(name):
        requested.append(name)
        assert name == "gemini"
        return provider

    monkeypatch.setattr(narrative_generation_service, "get_provider", get_configured_provider)
    result = narrative_generation_service.generate_narrative(package)
    assert result["status"] == "blocked"
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-model"
    assert "GEMINI_API_KEY" in result["message"]
    assert requested == ["gemini"]
    assert len(provider.requests) == 1


def test_gemini_failure_does_not_fall_back_to_ollama_or_openai(monkeypatch):
    package = _package()
    provider = _StubProvider("gemini", LLMResult("", "gemini", "configured-gemini-model", error="Gemini API request failed."))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini"))

    def gemini_only(name):
        assert name == "gemini"
        return provider

    monkeypatch.setattr(narrative_generation_service, "get_provider", gemini_only)
    result = narrative_generation_service.generate_narrative(package)
    assert result["status"] == "blocked"
    assert result["provider"] == "gemini"
    assert "Gemini API request failed" in result["message"]
    assert len(provider.requests) == 1


def test_ollama_adapter_preserves_temperature_and_output_transport(monkeypatch):
    provider = OllamaProvider()
    monkeypatch.setattr(provider, "is_available", lambda: True)
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "{}"}

    def post(url, json, timeout):
        captured.update({"url": url, "payload": json, "timeout": timeout})
        return _Response()

    monkeypatch.setattr("app.services.llm.ollama_provider.requests.post", post)
    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))
    assert result.text == "{}"
    assert captured["payload"]["options"] == {"temperature": 0.2, "num_predict": 700}


class _GeminiResponse:
    def __init__(self, text):
        self.text = text


def test_gemini_requests_json_schema_and_uses_provider_neutral_validation(monkeypatch):
    """Gemini's parsed object must still clear the package-aware shared gate."""
    package = _package()
    raw = _valid_output(package)
    provider = GeminiProvider()
    captured = {}

    class _Client:
        def generate_content(self, prompt, generation_config, request_options):
            captured.update({"prompt": prompt, "generation_config": generation_config, "request_options": request_options})
            return _GeminiResponse(raw)

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    original_generate = provider.generate

    def capture_request(request):
        captured["request"] = request
        return original_generate(request)

    monkeypatch.setattr(provider, "generate", capture_request)
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini"))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: provider)

    result = narrative_generation_service.generate_narrative(package)

    assert result["status"] == "generated"
    assert captured["generation_config"]["response_mime_type"] == "application/json"
    assert captured["generation_config"]["response_schema"] == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "narrative": {"type": "string"},
            "interpretation": {"type": "string"},
        },
        "required": ["title", "narrative"],
    }
    assert captured["request_options"] == {"timeout": 60, "retry": None}
    assert captured["generation_config"]["max_output_tokens"] == 8192
    assert captured["request"].video_id == "provider-test"
    assert captured["request"].evidence_items == len(package["events"])


def test_gemini_max_token_finish_reason_is_reported_as_truncated_json(monkeypatch):
    provider = GeminiProvider()

    class _Response:
        text = '{"title":"Incomplete"'
        candidates = [SimpleNamespace(
            finish_reason=2,
            content=SimpleNamespace(parts=[SimpleNamespace(text='{"title":"Incomplete"')]),
        )]

    class _Client:
        def generate_content(self, prompt, generation_config, request_options):
            assert generation_config["max_output_tokens"] == 4096
            return _Response()

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = provider.generate(StructuredGenerationRequest(
        prompt="validated prompt",
        max_tokens=4096,
        video_id="analysis-1",
        evidence_items=131,
    ))

    assert result.error_code == "GEMINI_OUTPUT_TRUNCATED"
    assert "output-token limit" in (result.error or "")


def test_gemini_rate_limit_retry_duration_supports_quota_hours():
    exc = RuntimeError(
        "429 You exceeded your quota. Please retry in 15h6m45.13696844s."
    )

    retry_after, error_code = _rate_limit_details(exc)

    assert retry_after == 54406
    assert error_code == "GEMINI_RATE_LIMITED"


def test_gemini_adapter_accepts_json_wrapped_in_markdown_fence(monkeypatch):
    provider = GeminiProvider()

    class _Client:
        def generate_content(self, prompt, generation_config, request_options):
            return _GeminiResponse('```json\n{"title":"Verified", "narrative":"Supported.", "used_event_ids":["event-1"]}\n```')

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))

    assert result.error is None
    assert result.structured_output == {
        "title": "Verified", "narrative": "Supported.", "used_event_ids": ["event-1"],
    }


def test_gemini_adapter_extracts_candidate_part_when_text_property_is_unavailable(monkeypatch):
    provider = GeminiProvider()

    class _Response:
        @property
        def text(self):
            raise ValueError("no convenience text")

        candidates = [SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text='{"title":"Verified", "narrative":"Supported.", "used_event_ids":["event-1"]}')]))]

    class _Client:
        def generate_content(self, prompt, generation_config, request_options):
            return _Response()

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))

    assert result.error is None
    assert result.structured_output["used_event_ids"] == ["event-1"]


def test_gemini_adapter_reconstructs_json_from_sdk_to_dict_candidate_parts(monkeypatch):
    """The legacy SDK's to_dict form is supported when quick accessors fail."""
    provider = GeminiProvider()

    class _Response:
        @property
        def text(self):
            raise ValueError("multiple candidates")

        @property
        def candidates(self):
            raise ValueError("candidate accessor unavailable")

        def to_dict(self):
            return {
                "candidates": [{
                    "content": {"parts": [
                        {"text": '{"title":"Verified", '},
                        {"text": '"narrative":"Supported.", "used_event_ids":["event-1"]}'},
                    ]},
                }],
            }

    class _Client:
        def generate_content(self, prompt, generation_config, request_options):
            return _Response()

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = provider.generate(StructuredGenerationRequest(prompt="validated prompt"))

    assert result.error is None
    assert result.structured_output == {
        "title": "Verified", "narrative": "Supported.", "used_event_ids": ["event-1"],
    }


def test_factory_defaults_to_gemini_and_explicitly_selects_gemini(monkeypatch):
    from app.services.llm import factory

    monkeypatch.setattr(factory, "settings", SimpleNamespace(story_llm_provider=""))
    assert factory.get_provider().name == "gemini"
    monkeypatch.setattr(factory, "settings", SimpleNamespace(story_llm_provider="gemini"))
    assert factory.get_provider().name == "gemini"


def test_production_configuration_rejects_non_gemini_story_provider(monkeypatch):
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(app_env="production", story_llm_provider="ollama"))
    with pytest.raises(narrative_generation_service.NarrativeGenerationValidationError, match="requires STORY_LLM_PROVIDER=gemini"):
        narrative_generation_service.configured_provider_metadata()


def test_missing_production_package_returns_before_gemini_is_called(monkeypatch):
    provider = _StubProvider("gemini", LLMResult("", "gemini", "gemini-model"))
    monkeypatch.setattr(
        story_integration_service,
        "get_modality_result",
        lambda *_: (_ for _ in ()).throw(AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")),
    )
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (provider, provider.name, provider.model))

    result = story_integration_service.generate_story_for_analysis("no-package-gemini-test")

    assert result["status"] == "unavailable"
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-model"
    assert provider.requests == []


@pytest.mark.parametrize("addition", ["Krishna appears.", "The performer dances.", "A conch is present.", "In a temple.", "Lyrics describe love."])
def test_provider_output_with_invented_claims_is_rejected(addition):
    package = _package()
    event = package["events"][0]
    raw = json.dumps({"title": "Verified sequence", "narrative": f"{event['statement']} {addition}", "used_event_ids": [event["event_id"]]})
    result = narrative_generation_service.generate_narrative(package, invoke=lambda _: raw)
    assert result["status"] == "blocked"
