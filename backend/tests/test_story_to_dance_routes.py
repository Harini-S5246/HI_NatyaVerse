"""API contract tests for the Story-to-Dance routes."""
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import stories, story_to_dance
from app.services import dance_generation_service, story_to_dance_service as service
from app.services.llm.base import LLMResult, StructuredGenerationRequest

client = TestClient(app)
KNOWLEDGE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "mudra_knowledge.json"


def test_existing_dance_to_story_route_remains_mounted():
    route = next(
        route for route in stories.router.routes
        if getattr(route, "path", None) == "/api/videos/{video_id}/story"
        and "POST" in getattr(route, "methods", set())
    )

    assert route.endpoint is stories.create_story
    assert route.endpoint.__module__ == "app.api.routes.stories"


def test_visual_reference_internal_error_is_logged_and_returns_structured_error(
    monkeypatch, caplog
):
    def fail_lookup(_request):
        raise RuntimeError("reference index failed")

    monkeypatch.setattr(story_to_dance, "get_scene_visual_references", fail_lookup)
    response = client.post(
        "/api/story-to-dance/stories/visual-references",
        json={
            "scenes": [{
                "scene_id": "scene-reference-error",
                "mudra_label": "Anjali",
                "bhava_label": None,
                "pose_label": None,
            }]
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "message": (
            "Reference lookup failed because the server encountered an internal error. "
            "Check backend logs using the scene IDs."
        ),
        "code": "STORY_DANCE_REFERENCE_LOOKUP_FAILED",
        "scene_ids": ["scene-reference-error"],
    }
    assert "scene-reference-error" in caplog.text
    assert "RuntimeError: reference index failed" in caplog.text


class _Provider:
    name = "gemini"
    model = "configured-test-model"

    def is_available(self):
        return True

    def generate(self, request):
        assert isinstance(request, StructuredGenerationRequest)
        return LLMResult(
            text="",
            provider=self.name,
            model=self.model,
            structured_output={
                "scenes": [{
                    "evidence_text": "A dancer offers a conch.",
                    "characters": ["A dancer"],
                    "action_type": "offer",
                    "action_text": "offers",
                    "objects": ["conch"],
                    "location": "",
                    "expressive_qualities": [],
                }]
            },
        )


def test_story_to_dance_api_creates_and_generates_an_isolated_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    def get_provider(name):
        assert name == "gemini"
        return _Provider()

    monkeypatch.setattr(service, "get_provider", get_provider)

    created = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": "A dancer offers a conch.", "language": "en", "title": "Offering"},
    )
    assert created.status_code == 201
    story = created.json()
    assert story["status"] == "ready_for_planning"
    assert story["dance_plan"] is None
    assert "video_id" not in story
    assert "analysis_id" not in story

    planned = client.post(f"/api/story-to-dance/stories/{story['story_id']}/plan")
    assert planned.status_code == 200
    record = planned.json()
    assert record["status"] == "plan_ready"
    assert record["dance_plan"]["story_id"] == story["story_id"]
    scene = record["dance_plan"]["scenes"][0]
    assert scene["dance_mapping"]["mudras"][0]["mudra"] == "Shanka"
    assert scene["scene_order"] == 1
    assert scene["source_text"] == "A dancer offers a conch."
    assert scene["character"] == ["A dancer"]
    assert scene["generator_label"] is None
    assert scene["generation_status"] == "unavailable"

    fetched = client.get(f"/api/story-to-dance/stories/{story['story_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["dance_plan"]["dance_plan_id"] == record["dance_plan"]["dance_plan_id"]


def test_one_click_workflow_persists_and_replays_idempotent_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(service, "get_provider", lambda name: _Provider())
    generation_calls = []

    def generate_performance(story_id, dance_plan_id):
        generation_calls.append((story_id, dance_plan_id))
        plan = service.get_story(story_id)["dance_plan"]
        scene = plan["scenes"][0]
        return {
            "generation_id": "66666666-6666-4666-8666-666666666666",
            "story_id": story_id,
            "dance_plan_id": dance_plan_id,
            "choreography_id": plan["choreography_id"],
            "status": "unavailable",
            "movement_coverage": {
                "generated_scenes": 0,
                "total_scenes": 1,
                "source_supported_scenes": 0,
            },
            "scenes": [{
                "scene_id": scene["scene_id"],
                "scene_order": 1,
                "status": "review_required",
                "generator_label": None,
                "mapping_status": "review_required",
                "movement_concepts": [],
                "candidate_adavu": None,
                "movement_sequence": [],
                "mudra": [],
                "action": scene["action"],
                "target": None,
                "direction": None,
                "transition": "No renderer output available.",
                "expressive_state": "neutral",
                "source_provenance": [],
                "reason": "Blender is unavailable.",
            }],
            "provenance": [],
            "reason": "Blender is unavailable.",
            "error_code": "MODEL_UNAVAILABLE",
            "limitations": ["The renderer requires Blender."],
        }

    monkeypatch.setattr(story_to_dance, "generate_dance_performance", generate_performance)
    request = {
        "request_id": "77777777-7777-4777-8777-777777777777",
        "story_text": "A dancer offers a conch.",
        "language": "en",
        "title": "Offering",
    }

    first = client.post("/api/story-to-dance/stories/workflow", json=request)
    assert first.status_code == 200
    result = first.json()
    assert result["story"]["status"] == "plan_ready"
    assert result["story"]["dance_plan"]["scenes"]
    assert result["generation"]["status"] == "unavailable"
    assert len(generation_calls) == 1

    replay = client.post("/api/story-to-dance/stories/workflow", json=request)
    assert replay.status_code == 200
    assert replay.json() == result
    assert len(generation_calls) == 1

    fetched = client.get(
        f"/api/story-to-dance/stories/workflow/{request['request_id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json() == result

    conflict = client.post(
        "/api/story-to-dance/stories/workflow",
        json={**request, "story_text": "A different story."},
    )
    assert conflict.status_code == 409


def test_story_to_dance_api_preserves_turn_return_components_and_provenance(monkeypatch, tmp_path):
    story_text = "A dancer enters a garden. She turns and returns to the center of the garden."
    scenes = [
        {
            "evidence_text": "A dancer enters a garden.",
            "characters": ["A dancer"],
            "action_type": "enter",
            "action_text": "enters a garden",
            "objects": [],
            "location": "garden",
            "expressive_qualities": [],
        },
        {
            "evidence_text": "She turns and returns to the center of the garden.",
            "characters": ["She"],
            "action_type": "turn",
            "action_text": "turns and returns to the center of the garden",
            "objects": [],
            "location": "center of the garden",
            "expressive_qualities": [],
        },
    ]

    class TwoSceneProvider:
        name = "gemini"
        model = "configured-test-model"

        def is_available(self):
            return True

        def generate(self, request):
            assert isinstance(request, StructuredGenerationRequest)
            return LLMResult(
                text="",
                provider=self.name,
                model=self.model,
                structured_output={"scenes": scenes},
            )

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(service, "get_provider", lambda name: TwoSceneProvider())

    created = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": story_text, "language": "en"},
    )
    planned = client.post(f"/api/story-to-dance/stories/{created.json()['story_id']}/plan")

    assert planned.status_code == 200
    scene = planned.json()["dance_plan"]["scenes"][1]
    assert scene["scene_order"] == 2
    assert scene["source_text"] == scenes[1]["evidence_text"]
    assert [
        (action["action"], action["direction"])
        for action in scene["movement_intent"]["actions"]
    ] == [("turn", "rotate"), ("return", "return")]
    assert [concept["concept"] for concept in scene["bharatanatyam_concept"]] == [
        "Bhramari",
        "Chari",
    ]
    assert [item["concept"] for item in scene["source_provenance"]] == [
        "Bhramari",
        "Chari",
    ]
    assert scene["candidate_adavu"] is None
    assert scene["generator_label"] is None
    assert scene["generation_status"] == "unavailable"


def test_performance_api_generates_playable_avatar_video_and_isolates_ids(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(
        dance_generation_service,
        "settings",
        SimpleNamespace(results_dir=tmp_path),
    )
    monkeypatch.setattr(service, "get_provider", lambda name: _Provider())

    generated_results = []
    for _ in range(2):
        created = client.post(
            "/api/story-to-dance/stories",
            json={"story_text": "A dancer offers a conch.", "language": "en"},
        )
        planned = client.post(f"/api/story-to-dance/stories/{created.json()['story_id']}/plan")
        assert planned.status_code == 200

        result = client.post(
            f"/api/story-to-dance/stories/{created.json()['story_id']}"
            f"/plans/{planned.json()['dance_plan']['dance_plan_id']}/performance"
        )
        assert result.status_code == 200
        payload = result.json()
        assert payload["status"] == "completed"
        assert payload["story_id"] == created.json()["story_id"]
        assert payload["dance_plan_id"] == planned.json()["dance_plan"]["dance_plan_id"]
        assert payload["choreography_id"] == planned.json()["dance_plan"]["choreography_id"]
        assert payload["generation_id"]
        assert payload["fps"] == 20
        assert payload["duration_seconds"] == 5
        assert payload["video_width"] == 720
        assert payload["video_height"] == 810
        assert payload["skeleton_format"] == "rigged_humanoid_3d_armature"
        assert payload["coordinate_convention"]
        assert len(payload["pose_sequence"]) == 100
        assert payload["visualization_type"] == "rigged_3d_humanoid"
        assert payload["video_url"]
        assert payload["frame_count"] == 100
        assert len(payload["scene_timings"]) == 1
        assert payload["movement_coverage"] == {
            "generated_scenes": 1,
            "total_scenes": len(planned.json()["dance_plan"]["scenes"]),
            "source_supported_scenes": 0,
        }
        assert payload["error_code"] is None
        assert payload["reason"] is None
        assert all(scene["generator_label"] is None for scene in payload["scenes"])
        assert payload["scenes"][0]["status"] == "generated"
        assert payload["scenes"][0]["mapping_status"] == "review_required"
        assert payload["scenes"][0]["candidate_adavu"] is None
        generated_results.append(payload)
        if len(generated_results) == 1:
            repeated = client.post(
                f"/api/story-to-dance/stories/{created.json()['story_id']}"
                f"/plans/{planned.json()['dance_plan']['dance_plan_id']}/performance"
            )
            assert repeated.status_code == 200
            assert repeated.json()["status"] == "completed"
            assert repeated.json()["generation_id"] != payload["generation_id"]

    assert generated_results[0]["story_id"] != generated_results[1]["story_id"]
    assert generated_results[0]["dance_plan_id"] != generated_results[1]["dance_plan_id"]
    assert generated_results[0]["choreography_id"] != generated_results[1]["choreography_id"]
    assert generated_results[0]["generation_id"] != generated_results[1]["generation_id"]
    video_response = client.get(generated_results[0]["video_url"])
    assert video_response.status_code == 200
    assert video_response.headers["content-type"].startswith("video/mp4")
    assert video_response.headers["accept-ranges"] == "bytes"
    assert int(video_response.headers["content-length"]) == len(video_response.content)
    video_path = tmp_path / "api_generated_avatar.mp4"
    video_path.write_bytes(video_response.content)
    assert video_response.content.startswith(b"\x00\x00\x00")
    ranged_all = client.get(generated_results[0]["video_url"], headers={"Range": "bytes=0-"})
    assert ranged_all.status_code == 206
    assert ranged_all.headers["content-range"] == (
        f"bytes 0-{len(video_response.content) - 1}/{len(video_response.content)}"
    )
    assert ranged_all.content == video_response.content
    ranged_small = client.get(
        generated_results[0]["video_url"],
        headers={"Range": "bytes=0-99"},
    )
    assert ranged_small.status_code == 206
    assert ranged_small.headers["content-range"] == f"bytes 0-99/{len(video_response.content)}"
    assert len(ranged_small.content) == 100
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    try:
        readable, frame = capture.read()
        assert readable
        assert frame.shape == (810, 720, 3)
    finally:
        capture.release()

    assert client.get(
        f"/api/story-to-dance/stories/{generated_results[0]['story_id']}"
        f"/plans/{generated_results[0]['dance_plan_id']}"
        f"/choreographies/{generated_results[1]['choreography_id']}"
        f"/generations/{generated_results[0]['generation_id']}/video"
    ).status_code == 404
    assert client.post(
        f"/api/story-to-dance/stories/{generated_results[0]['story_id']}"
        f"/plans/{generated_results[1]['dance_plan_id']}/performance"
    ).status_code == 409


def test_five_scene_story_renders_in_order_with_supported_concepts_and_review_statuses(
    monkeypatch, tmp_path
):
    story_text = (
        "A dancer enters a garden and sees a beautiful lotus. "
        "She raises her hands in Anjali as a respectful greeting. "
        "She then holds the lotus and looks at it with admiration. "
        "A conch is placed nearby, and she gestures toward the conch. "
        "She turns gracefully and returns to the center of the garden."
    )
    source_scenes = [
        ("A dancer enters a garden and sees a beautiful lotus.", "enter", "enters a garden", ["garden", "lotus"], "garden", "A dancer"),
        ("She raises her hands in Anjali as a respectful greeting.", "pray", "raises her hands in Anjali", ["hands"], "", "She"),
        ("She then holds the lotus and looks at it with admiration.", "look", "holds the lotus and looks at it", ["lotus"], "", "She"),
        ("A conch is placed nearby, and she gestures toward the conch.", "point", "gestures toward the conch", ["conch"], "", "she"),
        ("She turns gracefully and returns to the center of the garden.", "turn", "turns gracefully and returns to the center of the garden", [], "center of the garden", "She"),
    ]

    class FiveSceneProvider:
        name = "gemini"
        model = "configured-test-model"

        def is_available(self):
            return True

        def generate(self, request):
            assert isinstance(request, StructuredGenerationRequest)
            return LLMResult(
                text="",
                provider=self.name,
                model=self.model,
                structured_output={
                    "scenes": [
                        {
                            "evidence_text": text,
                            "characters": [character],
                            "action_type": action,
                            "action_text": action_text,
                            "objects": objects,
                            "location": location,
                            "expressive_qualities": [],
                        }
                        for text, action, action_text, objects, location, character in source_scenes
                    ]
                },
            )

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(
        dance_generation_service,
        "settings",
        SimpleNamespace(results_dir=tmp_path),
    )
    monkeypatch.setattr(service, "get_provider", lambda _: FiveSceneProvider())

    created = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": story_text, "language": "en"},
    )
    assert created.status_code == 201
    story_id = created.json()["story_id"]
    planned_response = client.post(f"/api/story-to-dance/stories/{story_id}/plan")
    assert planned_response.status_code == 200, planned_response.text
    plan = planned_response.json()["dance_plan"]

    assert [scene["scene_order"] for scene in plan["scenes"]] == [1, 2, 3, 4, 5]
    assert [scene["source_text"] for scene in plan["scenes"]] == [
        item[0] for item in source_scenes
    ]
    assert plan["scenes"][0]["location"] == "garden"
    assert plan["scenes"][0]["movement_intent"]["target"] == "garden"
    assert [concept["concept"] for concept in plan["scenes"][0]["bharatanatyam_concept"]] == ["Chari"]
    assert [concept["concept"] for concept in plan["scenes"][4]["bharatanatyam_concept"]] == [
        "Bhramari",
        "Chari",
    ]
    assert [
        scene["mapping_status"] for scene in plan["scenes"]
    ] == [
        "supported_concept",
        "review_required",
        "review_required",
        "review_required",
        "review_required",
    ]
    assert [
        (action["action"], action["direction"])
        for action in plan["scenes"][4]["movement_intent"]["actions"]
    ] == [("turn", "rotate"), ("return", "return")]
    assert all(scene["candidate_adavu"] is None for scene in plan["scenes"])
    assert any(item["mudra"] == "Anjali" for item in plan["scenes"][1]["mudra"])
    assert any(item["mudra"] == "Shanka" for item in plan["scenes"][3]["mudra"])

    response = client.post(
        f"/api/story-to-dance/stories/{story_id}"
        f"/plans/{plan['dance_plan_id']}/performance"
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["visualization_type"] == "rigged_3d_humanoid"
    assert result["movement_coverage"] == {
        "generated_scenes": 5,
        "total_scenes": 5,
        "source_supported_scenes": 2,
    }
    assert [scene["scene_order"] for scene in result["scenes"]] == [1, 2, 3, 4, 5]
    assert [scene["movement_concepts"] for scene in result["scenes"]] == [
        ["Chari"],
        [],
        [],
        [],
        ["Bhramari", "Chari"],
    ]
    assert all(scene["generator_label"] is None for scene in result["scenes"])
    assert all(scene["candidate_adavu"] is None for scene in result["scenes"])
    assert [scene["movement_sequence"] for scene in result["scenes"]] == [
        ["walk_forward", "face_direction", "form_alapadmam", "look_at_target"],
        ["raise_hands", "join_palms", "hold_anjali", "head_bow", "return_head"],
        ["reach_forward", "form_alapadmam", "hold_lotus", "look_at_target", "admiration"],
        ["turn_head", "gesture_toward_target", "form_shanka", "hold_gesture"],
        ["prepare_turn", "perform_bhramari", "return_to_center", "finish_pose"],
    ]
    assert [scene["mudra"] for scene in result["scenes"]] == [
        ["Alapadmam"],
        ["Anjali"],
        ["Alapadmam"],
        ["Shanka"],
        [],
    ]
    assert result["duration_seconds"] == 24
    assert result["frame_count"] == 480
    assert [scene["direction"] for scene in result["scenes"]] == [
        "forward",
        "upward",
        "toward_target",
        "toward_target",
        "rotate → return",
    ]
    assert [scene["expressive_state"] for scene in result["scenes"]] == [
        "neutral",
        "respectful",
        "admiration",
        "attention",
        "graceful",
    ]
    assert all(
        scene["source_provenance"] == plan["scenes"][scene["scene_order"] - 1]["source_provenance"]
        for scene in result["scenes"]
    )
    for generated_scene, planned_scene in zip(result["scenes"], plan["scenes"]):
        expected_targets = [
            action["target"] or "—"
            for action in planned_scene["movement_intent"]["actions"]
        ]
        if expected_targets:
            assert generated_scene["target"] == " → ".join(expected_targets)
        else:
            assert generated_scene["target"] == planned_scene["movement_intent"]["target"]
        first_frame = result["pose_sequence"][generated_scene["start_frame_index"]]["pose_data"]
        assert first_frame["source_provenance"] == planned_scene["source_provenance"]
        assert first_frame["candidate_adavu"] is None
    assert result["pose_sequence"][0]["pose_data"]["movement_concepts"] == ["Chari"]
    assert result["pose_sequence"][0]["pose_data"]["target"] == "garden"
    assert result["pose_sequence"][0]["pose_data"]["target_kind"] == "lotus"
    first_scene_intent = result["pose_sequence"][0]["pose_data"]["movement_intent"]
    assert first_scene_intent["action"] == "enter"
    assert first_scene_intent["target"] == "garden"
    assert first_scene_intent["direction"] == "forward"
    final_scene_start = result["scenes"][4]["start_frame_index"]
    final_scene_intent = result["pose_sequence"][final_scene_start]["pose_data"]["movement_intent"]
    assert [
        (action["action"], action["direction"])
        for action in final_scene_intent["actions"]
    ] == [("turn", "rotate"), ("return", "return")]
    final_scene_frame = result["scenes"][4]["end_frame_index"]
    assert result["pose_sequence"][final_scene_frame]["pose_data"]["rotation_degrees"] == 360
    previous_scene_end = result["pose_sequence"][result["scenes"][3]["end_frame_index"]]["pose_data"]
    final_scene_start_pose = result["pose_sequence"][final_scene_start]["pose_data"]
    return_phase_pose = result["pose_sequence"][final_scene_start + 14]["pose_data"]
    final_scene_pose = result["pose_sequence"][final_scene_frame]["pose_data"]
    assert final_scene_start_pose["x_offset"] == previous_scene_end["x_offset"] == 0
    assert return_phase_pose["x_offset"] < -45
    assert final_scene_pose["x_offset"] == 0

    video = client.get(result["video_url"])
    assert video.status_code == 200
    video_path = tmp_path / "five_scene_visualization.mp4"
    video_path.write_bytes(video.content)
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    try:
        assert capture.isOpened()
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == result["frame_count"]
        frames = []
        for frame_index in (
            0,
            result["scenes"][4]["start_frame_index"] + 12,
            result["scenes"][4]["start_frame_index"] + 24,
        ):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            readable, frame = capture.read()
            assert readable
            frames.append(frame)
        assert (frames[0] != frames[1]).any()
        assert (frames[1] != frames[2]).any()
    finally:
        capture.release()


def test_story_to_dance_api_rejects_empty_and_unsupported_language(monkeypatch, tmp_path):
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )

    empty = client.post("/api/story-to-dance/stories", json={"story_text": "  "})
    unsupported = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": "A story.", "language": "French"},
    )

    assert empty.status_code == 422
    assert empty.json()["code"] == "EMPTY_STORY"
    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "UNSUPPORTED_STORY_LANGUAGE"


def test_story_to_dance_get_refreshes_cached_movement_concepts_without_changing_ids(
    monkeypatch, tmp_path
):
    story_text = "A dancer enters a garden. She turns gracefully."
    scenes = [
        {
            "evidence_text": "A dancer enters a garden.",
            "characters": ["A dancer"],
            "action_type": "enter",
            "action_text": "enters",
            "objects": [],
            "location": "garden",
            "expressive_qualities": [],
        },
        {
            "evidence_text": "She turns gracefully.",
            "characters": ["She"],
            "action_type": "turn",
            "action_text": "turns gracefully",
            "objects": [],
            "location": "",
            "expressive_qualities": ["gracefully"],
        },
    ]

    class TwoSceneProvider:
        name = "gemini"
        model = "configured-test-model"

        def is_available(self):
            return True

        def generate(self, request):
            assert isinstance(request, StructuredGenerationRequest)
            return LLMResult(
                text="",
                provider=self.name,
                model=self.model,
                structured_output={"scenes": scenes},
            )

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(service, "get_provider", lambda _: TwoSceneProvider())

    created = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": story_text, "language": "en", "title": "Movement refresh"},
    )
    assert created.status_code == 201
    story_id = created.json()["story_id"]

    generated = client.post(f"/api/story-to-dance/stories/{story_id}/plan")
    assert generated.status_code == 200
    original = generated.json()["dance_plan"]
    record_path = service._story_path(story_id)
    persisted = service.load_json(record_path)

    for plan_scene in persisted["dance_plan"]["scenes"]:
        intent = plan_scene["dance_mapping"]["movement"]["movement_intent"]
        for key in (
            "movement_concept",
            "candidate_adavu",
            "mapping_status",
            "source_reference",
            "mapping_reason",
        ):
            intent.pop(key, None)
        intent.update({"movement_name": None, "status": "review_required", "source": None})
    for step in persisted["dance_plan"]["choreography"]:
        step["movement_intent"] = next(
            scene["dance_mapping"]["movement"]["movement_intent"]
            for scene in persisted["dance_plan"]["scenes"]
            if scene["scene_id"] == step["scene_id"]
        )
    persisted["dance_plan"]["movement_vocabulary"] = {
        "status": "unavailable",
        "message": "NO CURATED MOVEMENT RESOURCE FOUND",
        "entries": [],
        "source": None,
        "supported_actions": [],
        "supported_intents": [],
        "directions": [],
    }
    service.save_json(record_path, persisted)

    fetched = client.get(f"/api/story-to-dance/stories/{story_id}")

    assert fetched.status_code == 200
    refreshed = fetched.json()["dance_plan"]
    assert refreshed["dance_plan_id"] == original["dance_plan_id"]
    assert refreshed["choreography_id"] == original["choreography_id"]
    intents = [
        scene["dance_mapping"]["movement"]["movement_intent"]
        for scene in refreshed["scenes"]
    ]
    assert [intent["movement_concept"] for intent in intents] == ["Chari", "Bhramari"]
    assert [intent["mapping_status"] for intent in intents] == [
        "supported_concept",
        "supported_concept",
    ]
    assert all(intent["candidate_adavu"] is None for intent in intents)
    assert [step["movement_intent"]["movement_concept"] for step in refreshed["choreography"]] == [
        "Chari",
        "Bhramari",
    ]


def test_exact_seven_scene_story_generates_h264_video_with_ordered_movement_and_ranges(
    monkeypatch,
    tmp_path,
):
    story_text = (
        "A young dancer enters a beautiful garden and walks slowly toward a blooming lotus. "
        "She notices the lotus and gracefully opens her hands like a flower. "
        "She joins both palms in Anjali and respectfully bows her head. "
        "She then reaches toward the lotus, gently holds it, and looks at it with admiration. "
        "Suddenly, she notices a conch placed beside the lotus. "
        "She turns toward the conch and shows it with the Shanka mudra. "
        "Finally, she performs a graceful circular turn, walks back to the center of the garden, "
        "and ends in a calm standing pose with her hands in Anjali."
    )
    evidence = [
        "A young dancer enters a beautiful garden and walks slowly toward a blooming lotus.",
        "She notices the lotus and gracefully opens her hands like a flower.",
        "She joins both palms in Anjali and respectfully bows her head.",
        "She then reaches toward the lotus, gently holds it, and looks at it with admiration.",
        "Suddenly, she notices a conch placed beside the lotus.",
        "She turns toward the conch and shows it with the Shanka mudra.",
        "Finally, she performs a graceful circular turn, walks back to the center of the garden, and ends in a calm standing pose with her hands in Anjali.",
    ]
    actions = ["enter", "look", "pray", "look", "look", "turn", "turn"]
    objects = [
        ["garden", "lotus"],
        ["lotus", "hands", "flower"],
        ["palms", "Anjali", "head"],
        ["lotus"],
        ["conch", "lotus"],
        ["conch", "Shanka mudra"],
        ["circular turn", "center", "garden", "hands", "Anjali"],
    ]
    locations = ["garden", "", "", "", "", "", "center of the garden"]

    class ExactSevenSceneProvider:
        name = "gemini"
        model = "configured-test-model"

        def is_available(self):
            return True

        def generate(self, request):
            assert isinstance(request, StructuredGenerationRequest)
            return LLMResult(
                text="",
                provider=self.name,
                model=self.model,
                structured_output={
                    "scenes": [
                        {
                            "evidence_text": source,
                            "characters": ["A young dancer"] if order == 1 else ["She"],
                            "action_type": action,
                            "action_text": source,
                            "objects": scene_objects,
                            "location": location,
                            "expressive_qualities": [],
                        }
                        for order, (source, action, scene_objects, location) in enumerate(
                            zip(evidence, actions, objects, locations),
                            start=1,
                        )
                    ]
                },
            )

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    monkeypatch.setattr(
        dance_generation_service,
        "settings",
        SimpleNamespace(results_dir=tmp_path),
    )
    monkeypatch.setattr(service, "get_provider", lambda _: ExactSevenSceneProvider())

    created = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": story_text, "language": "en", "title": "Seven scene movement"},
    )
    assert created.status_code == 201
    story_id = created.json()["story_id"]
    planned_response = client.post(f"/api/story-to-dance/stories/{story_id}/plan")
    assert planned_response.status_code == 200, planned_response.text
    plan = planned_response.json()["dance_plan"]
    assert [scene["scene_order"] for scene in plan["scenes"]] == list(range(1, 8))
    assert [scene["source_text"] for scene in plan["scenes"]] == evidence
    assert plan["scenes"][0]["movement_intent"]["target"] == "garden"

    result_response = client.post(
        f"/api/story-to-dance/stories/{story_id}"
        f"/plans/{plan['dance_plan_id']}/performance"
    )
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    expected_sequences = [
        ["walk_forward", "face_direction", "form_alapadmam", "look_at_target"],
        ["turn_head_toward_target", "raise_hands", "open_hands", "form_alapadmam", "hold_alapadmam", "look_at_target"],
        ["raise_hands", "join_palms", "hold_anjali", "head_bow", "return_head"],
        ["step_or_lean_forward", "reach_forward", "form_alapadmam", "close_or_hold_lotus", "bring_lotus_toward_body", "look_at_target", "admiration_pose"],
        ["turn_head_toward_conch", "shift_body_attention", "gesture_toward_target", "prepare_shanka", "form_shanka", "hold_shanka"],
        ["turn_body_toward_conch", "perform_bhramari", "face_conch", "form_shanka", "hold_shanka"],
        ["perform_bhramari", "complete_turn", "walk_backward_or_return_to_center", "face_forward", "raise_hands", "join_palms", "hold_anjali", "final_pose"],
    ]
    assert result["status"] == "completed"
    assert result["story_id"] == story_id
    assert result["dance_plan_id"] == plan["dance_plan_id"]
    assert result["choreography_id"] == plan["choreography_id"]
    assert result["video_url"].endswith(f"/generations/{result['generation_id']}/video")
    assert [scene["movement_sequence"] for scene in result["scenes"]] == expected_sequences
    assert [scene["scene_order"] for scene in result["scenes"]] == list(range(1, 8))
    assert all(scene["status"] == "generated" for scene in result["scenes"])
    assert all(scene["candidate_adavu"] is None for scene in result["scenes"])
    assert [timing["scene_order"] for timing in result["scene_timings"]] == list(range(1, 8))
    assert result["fps"] == 20
    assert result["duration_seconds"] == 34
    assert result["frame_count"] == 680

    video_path = (
        dance_generation_service._generation_path(
            tmp_path,
            story_id,
            result["generation_id"],
        )
        / "dance-performance.mp4"
    )
    assert video_path.is_file()
    assert video_path.stat().st_size > 0
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    try:
        codec = int(capture.get(cv2.CAP_PROP_FOURCC)).to_bytes(
            4,
            "little",
        ).decode("ascii").strip("\x00").casefold()
        assert codec in {"h264", "avc1"}
        assert capture.get(cv2.CAP_PROP_FPS) == 20
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 680
        assert (capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) == (720, 810)
        first_ok, first = capture.read()
        capture.set(cv2.CAP_PROP_POS_FRAMES, 679)
        last_ok, last = capture.read()
        assert first_ok and last_ok
        assert (first != last).any()
        for scene in result["scenes"]:
            start = scene["start_frame_index"]
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            start_ok, start_frame = capture.read()
            capture.set(cv2.CAP_PROP_POS_FRAMES, start + (scene["end_frame_index"] - start) // 2)
            middle_ok, middle_frame = capture.read()
            assert start_ok and middle_ok
            assert (start_frame != middle_frame).any()
    finally:
        capture.release()

    video_response = client.get(result["video_url"])
    assert video_response.status_code == 200
    assert video_response.headers["content-type"].startswith("video/mp4")
    assert video_response.headers["accept-ranges"] == "bytes"
    assert int(video_response.headers["content-length"]) == video_path.stat().st_size
    assert video_response.content == video_path.read_bytes()
    all_range = client.get(result["video_url"], headers={"Range": "bytes=0-"})
    assert all_range.status_code == 206
    assert all_range.headers["content-range"] == (
        f"bytes 0-{video_path.stat().st_size - 1}/{video_path.stat().st_size}"
    )
    assert all_range.content == video_response.content
    small_range = client.get(result["video_url"], headers={"Range": "bytes=0-127"})
    assert small_range.status_code == 206
    assert small_range.headers["content-range"] == f"bytes 0-127/{video_path.stat().st_size}"
    assert small_range.content == video_path.read_bytes()[:128]

    second_story = client.post(
        "/api/story-to-dance/stories",
        json={"story_text": "A dancer enters a garden.", "language": "en"},
    )
    stale_video_url = result["video_url"].replace(
        story_id,
        second_story.json()["story_id"],
    )
    assert client.get(stale_video_url).status_code == 404
