from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app

client = TestClient(app)


def test_model_health_reports_runtime_metadata():
    status = {"mudra": {"loaded": True, "model": "Natya_Mudra_EfficientNetB0_FineTuned.keras", "classes": 48}}
    with patch("app.api.routes.health.model_manager.status", return_value=status):
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models"]["mudra"]["model"].endswith("Natya_Mudra_EfficientNetB0_FineTuned.keras")
    assert "loaded" in body["models"]["mudra"]


def test_dedicated_model_health_endpoint_exists():
    status = {name: {"loaded": True, "model": f"{name}.keras", "classes": 1} for name in ("mudra", "pose", "bhava")}
    with patch("app.api.routes.health.model_manager.status", return_value=status):
        response = client.get("/api/health/models")
    assert response.status_code == 200
    assert set(response.json()) == {"mudra", "pose", "bhava"}


def test_analyze_reports_missing_models_without_predictions():
    with patch("app.api.routes.analysis.model_manager.missing_models", return_value=["mudra", "bhava", "pose"]):
        response = client.post("/api/analyze", files={"video": ("dance.mp4", b"not-used", "video/mp4")})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "model_unavailable"
    assert set(body["missing_models"]) == {"mudra", "bhava", "pose"}


def test_upload_rejects_unsupported_type():
    response = client.post("/api/upload", files={"video": ("notes.txt", b"text", "text/plain")})
    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_invalid_video():
    response = client.post("/api/upload", files={"video": ("dance.mp4", b"not-a-video", "video/mp4")})
    assert response.status_code in {400, 503}
    assert response.json()["code"] in {"INVALID_VIDEO", "VIDEO_BACKEND_UNAVAILABLE"}


def test_frame_extraction_rejects_invalid_sampling_interval():
    response = client.post("/api/videos/missing/frames", json={"sampling_interval": 0})
    assert response.status_code == 422


def test_frame_extraction_reports_unknown_video():
    response = client.post("/api/videos/00000000-0000-0000-0000-000000000000/frames", json={"sampling_interval": 1})
    assert response.status_code == 404
    assert response.json()["code"] == "VIDEO_NOT_FOUND"


def test_result_not_found():
    response = client.get("/api/results/missing-result")
    assert response.status_code == 404
    assert response.json()["code"] == "RESULT_NOT_FOUND"
