"""Tests for the Story-to-Dance generator boundary and honest unavailable state."""
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError

from app.api.schemas.dance_generation import (
    DanceGenerationResult,
    DanceGenerationSceneStatus,
    DanceGeneratorOutput,
    GeneratorPoseFrame,
    GeneratorSceneResult,
    StoryDanceGenerationRequest,
    StoryDanceGenerationScene,
)
from app.services import dance_generation_service as service
from app.services import story_dance_avatar_service as avatar_service
from app.services.story_dance_avatar_service import (
    ProceduralDancerAvatarGenerator,
    RiggedBharatanatyamDancerGenerator,
    _scene_frame_count,
    _scene_movement_sequence,
)


def _request() -> StoryDanceGenerationRequest:
    return StoryDanceGenerationRequest(
        generation_id="44444444-4444-4444-4444-444444444444",
        story_id="11111111-1111-1111-1111-111111111111",
        dance_plan_id="55555555-5555-5555-5555-555555555555",
        choreography_id="22222222-2222-2222-2222-222222222222",
        output_directory=Path("generated"),
        scenes=[
            StoryDanceGenerationScene(
                scene_id="33333333-3333-3333-3333-333333333333",
                scene_order=1,
                source_text="A dancer enters a garden.",
                action="enters a garden",
                mudra=[],
                bhava=[],
                movement_concept=[],
                candidate_adavu=None,
                mapping_status="review_required",
                source_provenance=[],
                generator_label=None,
                duration_seconds=None,
            )
        ],
    )


def _saved_story_with_plan() -> dict:
    scene = _request().scenes[0].model_dump(mode="json")
    scene.update({
        "source_text": scene["source_text"],
        "action": scene["action"],
        "bharatanatyam_concept": scene.pop("movement_concept"),
        "duration_estimate_seconds": 5,
    })
    scene.pop("duration_seconds")
    plan = {
        "story_id": _request().story_id,
        "dance_plan_id": _request().dance_plan_id,
        "choreography_id": _request().choreography_id,
        "scenes": [scene],
    }
    return {
        "story_id": _request().story_id,
        "dance_plan": plan,
    }


def test_real_rigged_dancer_generator_is_required_when_available():
    generator = service.get_dance_generator()
    if generator is not None:
        assert isinstance(generator, RiggedBharatanatyamDancerGenerator)
    else:
        assert generator is None


def test_generation_storage_is_short_and_uniquely_scoped_to_story_and_generation(tmp_path: Path):
    request = _request()
    path = service._generation_path(
        tmp_path,
        request.story_id,
        request.generation_id,
    )

    assert path.parts[-2:] == (request.story_id, request.generation_id)
    assert len(str(path / "dance-performance.mp4")) < 260


def test_renderer_uses_planned_visualization_sequence_and_scene_duration():
    planned_scene = _request().scenes[0].model_copy(update={
        "visualization_sequence": [
            "Creative prayer gesture",
            "Bhramari turning concept (review required)",
        ],
        "duration_seconds": 3.5,
    })

    assert _scene_movement_sequence(planned_scene) == [
        "Creative prayer gesture",
        "Bhramari turning concept (review required)",
    ]
    assert _scene_frame_count(planned_scene, 1) == 70


def test_curated_plan_cues_expand_into_scene_specific_movement_phases():
    planned_scene = _request().scenes[0].model_copy(update={
        "visualization_sequence": [
            "Chari travel concept (review required)",
            "Alapadmam hasta (curated namesake only)",
        ],
    })

    assert _scene_movement_sequence(planned_scene) == [
        "walk_forward",
        "face_direction",
        "form_alapadmam",
        "look_at_target",
    ]


def test_generic_plan_cue_does_not_replace_a_source_grounded_anjali_sequence():
    planned_scene = _request().scenes[0].model_copy(update={
        "action": "joins both palms in Anjali and respectfully bows her head",
        "source_text": "She joins both palms in Anjali and respectfully bows her head.",
        "objects": ["palms", "Anjali"],
        "visualization_sequence": ["Creative story-action visualization"],
    })

    assert _scene_movement_sequence(planned_scene) == [
        "raise_hands",
        "join_palms",
        "hold_anjali",
        "head_bow",
        "return_head",
    ]


def test_generation_contract_rejects_invalid_fps():
    with pytest.raises(ValidationError):
        DanceGeneratorOutput.model_validate({
            "fps": 0,
            "duration_seconds": 1,
            "skeleton_format": "supplied by generator",
            "coordinate_convention": "supplied by generator",
            "generation_id": _request().generation_id,
            "story_id": _request().story_id,
            "dance_plan_id": _request().dance_plan_id,
            "choreography_id": _request().choreography_id,
            "pose_sequence": [{
                "frame_index": 0,
                "timestamp_seconds": 0,
                "pose_data": {"joint": [0, 0]},
            }],
            "video_path": "dance.mp4",
            "scenes": [{
                "scene_id": _request().scenes[0].scene_id,
                "scene_order": 1,
                "status": "generated",
                "generator_label": "example",
            }],
            "generator_name": "test",
            "generator_version": "test-version",
            "repository": "test",
            "license": "test",
            "provenance": ["test"],
        })


def test_completed_result_requires_real_video_and_pose_metadata():
    with pytest.raises(ValidationError, match="Completed generation requires"):
        DanceGenerationResult(
            generation_id="44444444-4444-4444-4444-444444444444",
            story_id=_request().story_id,
            dance_plan_id=_request().dance_plan_id,
            choreography_id=_request().choreography_id,
            status="completed",
            scenes=[
                DanceGenerationSceneStatus(
                    scene_id=_request().scenes[0].scene_id,
                    scene_order=1,
                    status="unavailable",
                    generator_label=None,
                    mapping_status="review_required",
                    movement_concepts=[],
                    candidate_adavu=None,
                    source_provenance=[],
                    movement_sequence=[],
                    mudra=[],
                    action="enter",
                    target=None,
                    transition="No renderer output available.",
                    expressive_state="neutral",
                )
            ],
            movement_coverage={
                "generated_scenes": 0,
                "total_scenes": 1,
                "source_supported_scenes": 0,
            },
            provenance=[],
            limitations=[],
        )


def test_generator_cannot_claim_unmapped_scene_as_generated(tmp_path: Path):
    request = _request()
    output = DanceGeneratorOutput(
        generation_id=request.generation_id,
        story_id=request.story_id,
        dance_plan_id=request.dance_plan_id,
        choreography_id=request.choreography_id,
        fps=24,
        duration_seconds=1,
        skeleton_format="generator declared",
        coordinate_convention="generator declared",
        pose_sequence=[
            GeneratorPoseFrame(
                frame_index=0,
                timestamp_seconds=0,
                pose_data={"sample": "test fixture"},
            )
        ],
        video_path=tmp_path / "not-created.mp4",
        scenes=[
            GeneratorSceneResult(
                scene_id=request.scenes[0].scene_id,
                scene_order=1,
                status="generated",
                generator_label="unvalidated-label",
                action="enter",
                transition="test transition",
                expressive_state="neutral",
            )
        ],
        generator_name="test adapter",
        generator_version="fixture",
        repository="test fixture",
        license="test fixture",
        provenance=["test fixture"],
    )

    with pytest.raises(service.DanceGenerationError, match="validated generator label"):
        service._validate_generator_output(output, request)

    mismatched_output = output.model_copy(
        update={"dance_plan_id": "66666666-6666-6666-6666-666666666666"}
    )
    with pytest.raises(service.DanceGenerationError, match="different generation or plan"):
        service._validate_generator_output(mismatched_output, request)


def test_legacy_procedural_avatar_is_rejected_for_final_generation(tmp_path: Path):
    request = _request().model_copy(update={"output_directory": tmp_path / "generation"})
    request.output_directory.mkdir()

    with pytest.raises(RuntimeError, match="intentionally disabled"):
        ProceduralDancerAvatarGenerator().generate(request)


def test_missing_blender_returns_actionable_unavailable_generation(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "settings", type("Settings", (), {"results_dir": tmp_path})())
    monkeypatch.setattr(service, "get_story", lambda story_id: _saved_story_with_plan())
    monkeypatch.setattr(service, "get_dance_generator", lambda: None)

    result = service.generate_dance_performance(_request().story_id, _request().dance_plan_id)

    assert result["status"] == "unavailable"
    assert result["error_code"] == "MODEL_UNAVAILABLE"
    assert "Blender is not available" in result["reason"]


def test_blender_render_failure_is_reported_without_video_success(monkeypatch, tmp_path):
    class BrokenGenerator:
        def generate(self, request):
            raise RuntimeError("Blender failed to render choreography: test failure")

    monkeypatch.setattr(service, "settings", type("Settings", (), {"results_dir": tmp_path})())
    monkeypatch.setattr(service, "get_story", lambda story_id: _saved_story_with_plan())
    monkeypatch.setattr(service, "get_dance_generator", lambda: BrokenGenerator())

    result = service.generate_dance_performance(_request().story_id, _request().dance_plan_id)

    assert result["status"] == "failed"
    assert result["error_code"] == "GENERATION_FAILED"
    assert "test failure" in result["reason"]
    assert result["video_url"] is None


def test_blender_failure_preserves_exit_code_stdout_and_stderr(monkeypatch, tmp_path):
    request = _request().model_copy(update={"output_directory": tmp_path / "generation"})
    request.output_directory.mkdir()
    monkeypatch.setattr(avatar_service, "_blender_executable", lambda: "blender.exe")
    command = []

    def fail_render(*args, **kwargs):
        command.extend(args[0])
        raise subprocess.CalledProcessError(
            7,
            args[0],
            output="Traceback: render script failed",
            stderr="TBBmalloc warning",
        )

    monkeypatch.setattr(avatar_service.subprocess, "run", fail_render)

    with pytest.raises(RuntimeError, match="exit code 7") as error:
        RiggedBharatanatyamDancerGenerator().generate(request)

    assert "Traceback: render script failed" in str(error.value)
    assert "TBBmalloc warning" in str(error.value)
    assert (request.output_directory / "blender.stdout.log").read_text() == (
        "Traceback: render script failed"
    )
    assert (request.output_directory / "blender.stderr.log").read_text() == (
        "TBBmalloc warning"
    )
    assert command[-1].endswith(".blender-script")
    assert not command[-1].endswith(".py")


def test_rigged_asset_generator_renders_real_humanoid_mp4(tmp_path: Path):
    request = _request().model_copy(update={"output_directory": tmp_path / "generation"})
    request.output_directory.mkdir()

    output = RiggedBharatanatyamDancerGenerator().generate(request)

    assert output.video_path.is_file()
    assert output.skeleton_format == "rigged_humanoid_3d_armature"
    assert output.pose_sequence[0].pose_data["representation"] == "rigged_3d_humanoid"
    assert output.scenes[0].status == "generated"
    assert output.duration_seconds == 5
    assert output.video_width == 720
    assert output.video_height == 810
    assert (request.output_directory / "blender_rigged_dancer.blender-script").is_file()
    assert output.generator_version == "2.0"
    assert "CC0 1.0" in output.license
    assert any("full-body armature" in item for item in output.provenance)


def test_character_asset_is_bundled_and_manifested_for_blender(tmp_path: Path):
    request = _request().model_copy(update={"output_directory": tmp_path / "generation"})
    request.output_directory.mkdir()

    script_path = avatar_service._build_blender_animation_script(
        request,
        request.output_directory / "frames",
    )
    manifest = json.loads(
        (request.output_directory / "render_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    script = script_path.read_text(encoding="utf-8")

    assert Path(manifest["character_asset_path"]).is_file()
    assert Path(manifest["character_asset_path"]).name == (
        "innerscene-female-base-cc0.glb"
    )
    assert "CC0HumanBaseBody" in script
    assert "StoryDanceControl_" in script
    assert "finger{finger_index}-{segment_index}.{side}" in script
