"""Tests for isolated, source-grounded Story-to-Dance planning."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.models.model_manager import model_manager
from app.services import story_to_dance_service as service
from app.services.llm.base import LLMResult, StructuredGenerationRequest

KNOWLEDGE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "mudra_knowledge.json"


class _Provider:
    name = "gemini"
    model = "configured-test-model"

    def __init__(self, output):
        self.output = output
        self.requests: list[StructuredGenerationRequest] = []
        self.available = True

    def is_available(self):
        return self.available

    def generate(self, request):
        assert isinstance(request, StructuredGenerationRequest)
        self.requests.append(request)
        if isinstance(self.output, LLMResult):
            return self.output
        if isinstance(self.output, str):
            return LLMResult(self.output, self.name, self.model)
        return LLMResult(
            json.dumps(self.output, ensure_ascii=False),
            self.name,
            self.model,
            structured_output=deepcopy(self.output),
        )


def _scenes():
    return {
        "scenes": [
            {
                "evidence_text": "Krishna enters the garden.",
                "characters": ["Krishna"],
                "action_type": "enter",
                "action_text": "enters",
                "objects": [],
                "location": "garden",
                "expressive_qualities": [],
            },
            {
                "evidence_text": "Krishna offers a conch.",
                "characters": ["Krishna"],
                "action_type": "offer",
                "action_text": "offers",
                "objects": ["conch"],
                "location": "",
                "expressive_qualities": [],
            },
            {
                "evidence_text": "Radha turns away shyly.",
                "characters": ["Radha"],
                "action_type": "turn",
                "action_text": "turns away",
                "objects": [],
                "location": "",
                "expressive_qualities": ["shyly"],
            },
        ]
    }


def test_visualization_sequence_preserves_story_action_order():
    sequence = service._visualization_sequence(
        {
            "evidence_text": (
                "The devotee prayed. Suddenly divine light appeared, and Shiva blessed her."
            ),
            "action_text": (
                "prayed, then divine light appeared and Shiva blessed her"
            ),
            "expressive_qualities": [],
        },
        [],
        {"actions": []},
    )

    assert sequence == [
        "Creative prayer gesture",
        "Creative divine-appearance lighting cue",
        "Creative blessing gesture",
    ]


def _wire(monkeypatch, tmp_path, output=None):
    provider = _Provider(output if output is not None else _scenes())
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(results_dir=tmp_path, mudra_knowledge_path=KNOWLEDGE),
    )
    def get_provider(name):
        assert name == "gemini"
        return provider

    monkeypatch.setattr(service, "get_provider", get_provider)
    return provider


def test_each_story_has_its_own_persisted_identity(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    first = service.create_story("The first story.", title="First")
    second = service.create_story("The second story.", title="Second")

    assert first["story_id"] != second["story_id"]
    assert service.get_story(first["story_id"])["story_text"] == "The first story."
    assert service.get_story(second["story_id"])["story_text"] == "The second story."
    assert (tmp_path / "story_to_dance" / f"{first['story_id']}.json").is_file()
    assert (tmp_path / "story_to_dance" / f"{second['story_id']}.json").is_file()


def test_plan_preserves_story_order_and_only_directly_curated_mudra_matches(monkeypatch, tmp_path):
    provider = _wire(monkeypatch, tmp_path)
    story = service.create_story(
        "Krishna enters the garden. Krishna offers a conch. Radha turns away shyly.",
        language="English",
    )
    result = service.generate_dance_plan(story["story_id"])
    plan = result["dance_plan"]

    assert result["status"] == "plan_ready"
    assert [scene["order"] for scene in plan["scenes"]] == [1, 2, 3]
    assert [step["order"] for step in plan["choreography"]] == [1, 2, 3]
    assert [step["scene_id"] for step in plan["choreography"]] == [
        scene["scene_id"] for scene in plan["scenes"]
    ]
    assert all(scene["story_id"] == story["story_id"] for scene in plan["scenes"])
    assert plan["scenes"][1]["dance_mapping"]["mudras"][0]["mudra"] == "Shanka"
    assert plan["scenes"][2]["dance_mapping"]["bhava"] == [{
        "expressive_quality": "shyly",
        "bhava": None,
        "status": "unmapped",
        "note": service._UNMAPPED_BHAVA_NOTE,
    }]
    assert all(step["movement_status"] == "review_required" for step in plan["choreography"])
    assert all(step["adavu"] is None and step["pose"] is None for step in plan["choreography"])
    assert plan["pose_sequence"]["status"] == "not_generated"
    assert plan["pose_sequence"]["items"] == []
    assert plan["generated_performance"]["status"] == "not_generated"
    assert plan["generated_performance"]["video_url"] is None
    assert len(provider.requests) == 1
    assert provider.requests[0].video_id is None


def test_characters_are_exact_spans_from_each_scene_and_pronouns_stay_verbatim(monkeypatch, tmp_path):
    story_text = (
        "A dancer enters a garden and sees a beautiful lotus. "
        "She raises her hands in Anjali as a respectful greeting. "
        "She then holds the lotus and looks at it with admiration."
    )
    output = {
        "scenes": [
            {
                "evidence_text": "A dancer enters a garden and sees a beautiful lotus.",
                "characters": ["A dancer"],
                "action_type": "enter",
                "action_text": "enters a garden",
                "objects": ["lotus"],
                "location": "garden",
                "expressive_qualities": ["beautiful"],
            },
            {
                "evidence_text": "She raises her hands in Anjali as a respectful greeting.",
                "characters": ["She"],
                "action_type": "offer",
                "action_text": "raises her hands in Anjali as a respectful greeting",
                "objects": ["Anjali"],
                "location": "",
                "expressive_qualities": [],
            },
            {
                "evidence_text": "She then holds the lotus and looks at it with admiration.",
                "characters": ["She"],
                "action_type": "look",
                "action_text": "holds the lotus and looks at it with admiration",
                "objects": ["lotus"],
                "location": "",
                "expressive_qualities": ["admiration"],
            },
        ]
    }
    _wire(monkeypatch, tmp_path, output)
    story = service.create_story(story_text)

    scenes = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"]

    assert [scene["characters"] for scene in scenes] == [["A dancer"], ["She"], ["She"]]
    assert [scene["narrative_text"] for scene in scenes] == [
        item["evidence_text"] for item in output["scenes"]
    ]
    assert scenes[0]["dance_mapping"]["movement"]["movement_intent"]["target"] == "garden"
    assert [
        mapping["mudra"]
        for mapping in scenes[0]["dance_mapping"]["mudras"]
        if mapping["status"] == "mapped"
    ] == ["Alapadmam"]
    assert all(
        mapping["mudra"] != "Tripathaka"
        for mapping in scenes[2]["dance_mapping"]["mudras"]
    )


def test_character_absent_from_scene_is_rejected_even_if_present_in_another_scene(
    monkeypatch, tmp_path
):
    output = {
        "scenes": [
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
                "evidence_text": "The lotus shines.",
                "characters": ["A dancer"],
                "action_type": "other",
                "action_text": "shines",
                "objects": ["lotus"],
                "location": "",
                "expressive_qualities": [],
            },
        ]
    }
    _wire(monkeypatch, tmp_path, output)
    story = service.create_story("A dancer enters a garden. The lotus shines.")

    with pytest.raises(AppError, match="character that is not present") as error:
        service.generate_dance_plan(story["story_id"])

    assert error.value.status_code == 502


def test_empty_character_list_is_allowed_when_scene_has_no_character_reference(
    monkeypatch, tmp_path
):
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": "A lotus rests nearby.",
            "characters": [],
            "action_type": "other",
            "action_text": "rests nearby",
            "objects": ["lotus"],
            "location": "",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story("A lotus rests nearby.")

    scenes = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"]

    assert scenes[0]["characters"] == []


def test_character_must_be_verbatim_in_its_quoted_scene(monkeypatch, tmp_path, caplog):
    evidence = "A dancer enters a garden and sees a beautiful lotus."
    provider = _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["She"],
            "action_type": "enter",
            "action_text": "enters a garden",
            "objects": ["lotus"],
            "location": "garden",
            "expressive_qualities": ["beautiful"],
        }]
    })
    story = service.create_story(evidence)

    with pytest.raises(AppError, match="character that is not present") as error:
        service.generate_dance_plan(story["story_id"])

    assert error.value.status_code == 502
    assert "exact contiguous string appears inside that scene's evidence_text" in provider.requests[0].prompt
    assert "Do not infer, resolve, normalize, expand, paraphrase, or carry characters between scenes." in provider.requests[0].prompt
    schema_description = provider.requests[0].response_schema["properties"]["scenes"]["items"]["properties"]["characters"]["description"]
    assert "inside that same scene's evidence_text" in schema_description
    assert "Do not use a character from another scene." in schema_description
    assert "source_span_not_found field=character value='She'" in caplog.text


def test_enter_target_uses_scene_location_not_object(monkeypatch, tmp_path):
    evidence = "A dancer enters a garden and sees a beautiful lotus."
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["A dancer"],
            "action_type": "enter",
            "action_text": "enters a garden and sees a beautiful lotus",
            "objects": ["lotus"],
            "location": "garden",
            "expressive_qualities": ["beautiful"],
        }]
    })
    story = service.create_story(evidence)

    movement = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"][0]["dance_mapping"]["movement"]

    assert movement["movement_intent"]["action"] == "enter"
    assert movement["movement_intent"]["target"] == "garden"
    assert movement["movement_intent"]["direction"] == "forward"
    assert movement["movement_name"] is None
    assert movement["movement_intent"]["movement_concept"] == "Chari"
    assert movement["movement_intent"]["mapping_status"] == "supported_concept"
    assert movement["movement_intent"]["candidate_adavu"] is None
    assert movement["status"] == "review_required"
    assert movement["movement_vocabulary"]["status"] == "review_required"
    assert movement["movement_intent"]["target"] != "lotus"


def test_entry_movement_intent_stays_separate_from_adavu_lookup(monkeypatch, tmp_path):
    evidence = "A dancer enters a garden and sees a beautiful lotus."
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["A dancer"],
            "action_type": "enter",
            "action_text": "enters a garden and sees a beautiful lotus",
            "objects": ["lotus"],
            "location": "garden",
            "expressive_qualities": ["beautiful"],
        }]
    })
    story = service.create_story(evidence)

    plan = service.generate_dance_plan(story["story_id"])["dance_plan"]
    scene = plan["scenes"][0]
    movement = scene["dance_mapping"]["movement"]

    assert scene["objects"] == ["lotus"]
    assert scene["location"] == "garden"
    assert movement["movement_intent"]["action"] == "enter"
    assert movement["movement_intent"]["target"] == "garden"
    assert movement["movement_intent"]["movement_concept"] == "Chari"
    assert movement["movement_intent"]["candidate_adavu"] is None
    assert movement["movement_name"] is None
    assert movement["movement_intent"]["mapping_status"] == "supported_concept"
    assert movement["movement_vocabulary"]["status"] == "review_required"
    assert plan["movement_vocabulary"]["status"] == "review_required"


def test_conch_maps_to_curated_shanka(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": "Krishna offers a conch.",
            "characters": ["Krishna"],
            "action_type": "offer",
            "action_text": "offers a conch",
            "objects": ["conch"],
            "location": "",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story("Krishna offers a conch.")

    mapping = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"][0]["dance_mapping"]["mudras"][0]

    assert mapping["mudra"] == "Shanka"
    assert mapping["meaning"] == "Conch"
    assert mapping["status"] == "mapped"


@pytest.mark.parametrize("concept", ["salutation", "namaskara"])
def test_salutation_and_namaskara_map_to_curated_anjali(concept, monkeypatch, tmp_path):
    evidence = f"A dancer offers a {concept}."
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["A dancer"],
            "action_type": "offer",
            "action_text": f"offers a {concept}",
            "objects": [],
            "location": "",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story(evidence)

    mapping = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"][0]["dance_mapping"]["mudras"][0]

    assert mapping["mudra"] == "Anjali"
    assert mapping["meaning"] == "Salutation (namaskara)"
    assert mapping["status"] == "mapped"


def test_story_example_keeps_direct_mudras_without_tripathaka_false_positive(monkeypatch, tmp_path):
    story_text = (
        "A dancer enters a garden and sees a beautiful lotus. "
        "She raises her hands in Anjali as a respectful greeting. "
        "She then holds the lotus and looks at it with admiration. "
        "A conch is placed nearby, and she gestures toward the conch. "
        "She turns gracefully and returns to the center of the garden."
    )
    output = {
        "scenes": [
            {
                "evidence_text": "A dancer enters a garden and sees a beautiful lotus.",
                "characters": ["A dancer"],
                "action_type": "enter",
                "action_text": "enters a garden and sees a beautiful lotus",
                "objects": ["lotus"],
                "location": "garden",
                "expressive_qualities": ["beautiful"],
            },
            {
                "evidence_text": "She raises her hands in Anjali as a respectful greeting.",
                "characters": ["She"],
                "action_type": "offer",
                "action_text": "raises her hands in Anjali as a respectful greeting",
                "objects": ["Anjali"],
                "location": "",
                "expressive_qualities": ["respectful"],
            },
            {
                "evidence_text": "She then holds the lotus and looks at it with admiration.",
                "characters": ["She"],
                "action_type": "look",
                "action_text": "holds the lotus and looks at it with admiration",
                "objects": ["lotus"],
                "location": "",
                "expressive_qualities": ["admiration"],
            },
            {
                "evidence_text": "A conch is placed nearby, and she gestures toward the conch.",
                "characters": ["she"],
                "action_type": "point",
                "action_text": "gestures toward the conch",
                "objects": ["conch"],
                "location": "",
                "expressive_qualities": [],
            },
            {
                "evidence_text": "She turns gracefully and returns to the center of the garden.",
                "characters": ["She"],
                "action_type": "turn",
                "action_text": "turns gracefully and returns to the center of the garden",
                "objects": [],
                "location": "center of the garden",
                "expressive_qualities": ["gracefully"],
            },
        ]
    }
    _wire(monkeypatch, tmp_path, output)
    record = service.create_story(story_text)

    plan = service.generate_dance_plan(record["story_id"])["dance_plan"]
    scenes = plan["scenes"]

    assert [scene["order"] for scene in scenes] == [1, 2, 3, 4, 5]
    assert [scene["narrative_text"] for scene in scenes] == [
        item["evidence_text"] for item in output["scenes"]
    ]
    assert [scene["scene_order"] for scene in scenes] == [1, 2, 3, 4, 5]
    assert [scene["source_text"] for scene in scenes] == [
        item["evidence_text"] for item in output["scenes"]
    ]
    assert [mapping["mudra"] for mapping in scenes[0]["dance_mapping"]["mudras"] if mapping["status"] == "mapped"] == ["Alapadmam"]
    assert [mapping["mudra"] for mapping in scenes[1]["dance_mapping"]["mudras"] if mapping["status"] == "mapped"] == ["Anjali"]
    assert [mapping["mudra"] for mapping in scenes[2]["dance_mapping"]["mudras"] if mapping["status"] == "mapped"] == ["Alapadmam"]
    assert all(mapping["mudra"] != "Tripathaka" for mapping in scenes[2]["dance_mapping"]["mudras"])
    assert [mapping["mudra"] for mapping in scenes[3]["dance_mapping"]["mudras"] if mapping["status"] == "mapped"] == ["Shanka"]
    assert [step["source_quote"] for step in plan["choreography"]] == [scene["narrative_text"] for scene in scenes]
    assert [step["story_action"] for step in plan["choreography"]] == [scene["action_text"] for scene in scenes]
    assert [step["objects"] for step in plan["choreography"]] == [scene["objects"] for scene in scenes]
    assert [step["location"] for step in plan["choreography"]] == [scene["location"] for scene in scenes]
    assert [step["source_expressions"] for step in plan["choreography"]] == [scene["expressive_qualities"] for scene in scenes]
    assert len({plan["story_id"], plan["dance_plan_id"], plan["choreography_id"]}) == 3
    assert len({scene["scene_id"] for scene in scenes}) == len(scenes)
    assert all(step["adavu"] is None and step["pose"] is None for step in plan["choreography"])
    assert all(step["movement_status"] == "review_required" for step in plan["choreography"])
    final_scene = scenes[4]
    final_intent = final_scene["movement_intent"]
    assert final_intent["action"] == "turn_and_return"
    assert final_intent["direction"] == "rotate_then_return"
    assert [(item["action"], item["direction"]) for item in final_intent["actions"]] == [
        ("turn", "rotate"),
        ("return", "return"),
    ]
    assert final_intent["actions"][1]["target"] == "center of the garden"
    assert "enter" not in [item["action"] for item in final_intent["actions"]]
    assert final_intent["movement_concept"] is None
    assert [item["movement_concept"] for item in final_intent["actions"]] == [
        "Bhramari",
        "Chari",
    ]
    assert [item["action"] for item in final_scene["bharatanatyam_concept"]] == [
        "turn",
        "return",
    ]
    assert [item["concept"] for item in final_scene["bharatanatyam_concept"]] == [
        "Bhramari",
        "Chari",
    ]
    assert [item["concept"] for item in final_scene["source_provenance"]] == [
        "Bhramari",
        "Chari",
    ]
    assert final_scene["mapping_status"] == "review_required"
    assert final_scene["candidate_adavu"] is None
    assert final_scene["generator_label"] is None
    assert final_scene["generation_status"] == "unavailable"
    assert plan["pose_sequence"] == {
        "status": "not_generated",
        "items": [],
        "message": (
            "No validated pose-sequence generator is configured. The available pose model "
            "is a classifier and cannot generate dance poses."
        ),
    }
    assert plan["generated_performance"]["status"] == "not_generated"
    assert plan["generated_performance"]["video_url"] is None


def test_source_backed_movement_concepts_stay_separate_from_adavus_and_mudras(
    monkeypatch, tmp_path
):
    story_text = (
        "A dancer enters a garden and sees a beautiful lotus. "
        "She raises her hands in Anjali as a respectful greeting. "
        "She looks at the lotus with admiration. "
        "She gestures toward the conch. "
        "She turns gracefully."
    )
    output = {
        "scenes": [
            {
                "evidence_text": "A dancer enters a garden and sees a beautiful lotus.",
                "characters": ["A dancer"],
                "action_type": "enter",
                "action_text": "enters a garden",
                "objects": ["lotus"],
                "location": "garden",
                "expressive_qualities": ["beautiful"],
            },
            {
                "evidence_text": "She raises her hands in Anjali as a respectful greeting.",
                "characters": ["She"],
                "action_type": "express",
                "action_text": "raises her hands in Anjali",
                "objects": ["Anjali"],
                "location": "",
                "expressive_qualities": ["respectful"],
            },
            {
                "evidence_text": "She looks at the lotus with admiration.",
                "characters": ["She"],
                "action_type": "look",
                "action_text": "looks at the lotus",
                "objects": ["lotus"],
                "location": "",
                "expressive_qualities": ["admiration"],
            },
            {
                "evidence_text": "She gestures toward the conch.",
                "characters": ["She"],
                "action_type": "point",
                "action_text": "gestures toward the conch",
                "objects": ["conch"],
                "location": "",
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
    }
    _wire(monkeypatch, tmp_path, output)
    record = service.create_story(story_text)

    plan = service.generate_dance_plan(record["story_id"])["dance_plan"]
    scenes = plan["scenes"]
    intents = [
        scene["dance_mapping"]["movement"]["movement_intent"]
        for scene in scenes
    ]

    assert [(intent["action"], intent["direction"]) for intent in intents] == [
        ("enter", "forward"),
        ("raise_hands", "upward"),
        ("look", "toward_target"),
        ("gesture", "toward_target"),
        ("turn", "rotate"),
    ]
    assert [intent["movement_concept"] for intent in intents] == [
        "Chari", None, None, None, "Bhramari"
    ]
    assert [intent["mapping_status"] for intent in intents] == [
        "supported_concept",
        "review_required",
        "review_required",
        "review_required",
        "supported_concept",
    ]
    assert all(intent["candidate_adavu"] is None for intent in intents)
    assert all(intent["movement_name"] is None for intent in intents)
    assert all(
        scene["generator_label"] is None
        and scene["generation_status"] == "unavailable"
        for scene in scenes
    )
    assert all(scene["candidate_adavu"] is None for scene in scenes)
    assert all(
        scene["mapping_status"] == "review_required"
        for scene in scenes[1:4]
    )
    assert intents[0]["target"] == "garden"
    assert scenes[0]["objects"] == ["lotus"]
    assert [scene["characters"] for scene in scenes] == [
        ["A dancer"], ["She"], ["She"], ["She"], ["She"]
    ]
    assert [
        item["mudra"]
        for item in scenes[0]["dance_mapping"]["mudras"]
        if item["status"] == "mapped"
    ] == ["Alapadmam"]
    assert [
        item["mudra"]
        for item in scenes[1]["dance_mapping"]["mudras"]
        if item["status"] == "mapped"
    ] == ["Anjali"]
    assert [
        item["mudra"]
        for item in scenes[2]["dance_mapping"]["mudras"]
        if item["status"] == "mapped"
    ] == ["Alapadmam"]
    assert all(
        item["mudra"] != "Tripathaka"
        for item in scenes[2]["dance_mapping"]["mudras"]
    )
    assert [
        item["mudra"]
        for item in scenes[3]["dance_mapping"]["mudras"]
        if item["status"] == "mapped"
    ] == ["Shanka"]
    assert intents[0]["source"] == "Eambalam, The Structure of Bharathanatyam"
    assert "Chari" in intents[0]["source_reference"]
    assert intents[4]["source"] == "Kalaprangan Trust, Bharatanatyam Praveshika Purna"
    assert "Bhramari" in intents[4]["source_reference"]
    assert intents[1]["mapping_reason"] == "No source-grounded movement mapping is currently available."
    assert all(step["movement_intent"] == intent for step, intent in zip(plan["choreography"], intents))


def test_story_plan_does_not_use_pose_classifier_as_a_generator(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": "Krishna enters the garden.",
            "characters": ["Krishna"],
            "action_type": "enter",
            "action_text": "enters the garden",
            "objects": [],
            "location": "garden",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story("Krishna enters the garden.")

    def reject_pose_model(name):
        assert name != "pose", "The pose classifier must not be used as a generator."
        raise AssertionError(f"Unexpected model access: {name}")

    monkeypatch.setattr(model_manager, "get", reject_pose_model)
    plan = service.generate_dance_plan(story["story_id"])["dance_plan"]

    assert plan["scenes"][0]["generator_label"] is None
    assert plan["scenes"][0]["generation_status"] == "unavailable"
    assert plan["pose_sequence"]["status"] == "not_generated"
    assert plan["generated_performance"]["status"] == "not_generated"


def test_vocabulary_entries_include_provenance_and_no_adavu_action_mapping():
    vocabulary = service._curated_movement_vocabulary()

    assert vocabulary["status"] == "review_required"
    assert vocabulary["entries"]
    assert all(
        entry["movement_name"]
        and entry["movement_type"] in {"adavu", "movement_concept"}
        and isinstance(entry["supported_intents"], list)
        and entry["mapping_status"] in {"supported_concept", "review_required"}
        and entry["source"]
        and entry["source_reference"]
        and entry["notes"]
        for entry in vocabulary["entries"]
    )
    assert not any(
        entry["movement_type"] == "adavu" and entry["supported_intents"]
        for entry in vocabulary["entries"]
    )
    assert not any(
        entry["movement_type"] == "adavu" and entry["mapping_status"] == "supported_concept"
        for entry in vocabulary["entries"]
    )


def test_generic_action_phrase_is_preserved_and_left_for_choreographer_review(monkeypatch, tmp_path):
    action = "gestures toward a flower"
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": f"Krishna {action}.",
            "characters": ["Krishna"],
            "action_type": "other",
            "action_text": action,
            "objects": ["flower"],
            "location": "",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story(f"Krishna {action}.")

    plan = service.generate_dance_plan(story["story_id"])["dance_plan"]
    scene = plan["scenes"][0]

    assert scene["action_text"] == action
    assert scene["dance_mapping"]["movement"]["action_type"] == "other"
    assert scene["dance_mapping"]["movement"]["status"] == "review_required"
    assert scene["dance_mapping"]["movement"]["adavu"] is None
    assert scene["dance_mapping"]["mudras"][0]["status"] == "unsupported"
    assert plan["choreography"][0]["story_action"] == action
    assert plan["choreography"][0]["adavu"] is None
    assert plan["pose_sequence"]["items"] == []
    assert plan["generated_performance"]["video_url"] is None


def test_choreography_step_has_movement_intent_without_fake_adavu(monkeypatch, tmp_path):
    evidence = "Krishna enters a garden and gestures toward a flower."
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["Krishna"],
            "action_type": "enter",
            "action_text": "enters a garden and gestures toward a flower",
            "objects": ["flower"],
            "location": "garden",
            "expressive_qualities": [],
        }]
    })
    story = service.create_story(evidence)

    plan = service.generate_dance_plan(story["story_id"])["dance_plan"]
    step = plan["choreography"][0]
    movement = plan["scenes"][0]["dance_mapping"]["movement"]

    assert step["source_quote"] == evidence
    assert step["movement_intent"]["action"] == "enter"
    assert step["movement_intent"]["movement_name"] is None
    assert step["movement_intent"]["status"] == "supported"
    assert step["movement_intent"]["movement_concept"] == "Chari"
    assert step["movement_intent"]["candidate_adavu"] is None
    assert movement["movement_intent"]["action"] == "enter"
    assert movement["movement_name"] is None
    assert movement["status"] == "review_required"


@pytest.mark.parametrize("qualities", [["shy"], ["happy"], ["affection"]])
def test_source_expressions_are_not_converted_to_bhava(qualities, monkeypatch, tmp_path):
    evidence = "Radha feels shy and happy, and shows affection."
    _wire(monkeypatch, tmp_path, {
        "scenes": [{
            "evidence_text": evidence,
            "characters": ["Radha"],
            "action_type": "express",
            "action_text": "feels",
            "objects": [],
            "location": "",
            "expressive_qualities": qualities,
        }]
    })
    story = service.create_story(evidence)

    mappings = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"][0]["dance_mapping"]["bhava"]

    assert [item["expressive_quality"] for item in mappings] == qualities
    assert all(item["bhava"] is None and item["status"] == "unmapped" for item in mappings)


def test_unknown_mudra_bhava_and_movement_are_not_fabricated(monkeypatch, tmp_path):
    output = _scenes()
    output["scenes"][1]["evidence_text"] = "Krishna offers a flower."
    output["scenes"][1]["objects"] = ["flower"]
    provider = _wire(monkeypatch, tmp_path, output)
    story = service.create_story(
        "Krishna enters the garden. Krishna offers a flower. Radha turns away shyly."
    )

    plan = service.generate_dance_plan(story["story_id"])["dance_plan"]
    mapping = plan["scenes"][1]["dance_mapping"]

    assert mapping["mudra_status"] == "unsupported"
    assert mapping["mudras"][0]["status"] == "unsupported"
    assert mapping["mudras"][0]["mudra"] is None
    assert mapping["movement"]["adavu"] is None
    assert mapping["movement"]["status"] == "review_required"
    assert plan["scenes"][2]["dance_mapping"]["bhava"][0]["bhava"] is None
    assert len(provider.requests) == 1


def test_lotus_maps_only_to_the_curated_lotus_meaning(monkeypatch, tmp_path):
    output = {
        "scenes": [{
            "evidence_text": "A dancer shows a lotus.",
            "characters": ["A dancer"],
            "action_type": "other",
            "action_text": "shows",
            "objects": ["lotus"],
            "location": "",
            "expressive_qualities": [],
        }]
    }
    _wire(monkeypatch, tmp_path, output)
    story = service.create_story("A dancer shows a lotus.")

    mapping = service.generate_dance_plan(story["story_id"])["dance_plan"]["scenes"][0]["dance_mapping"]

    assert mapping["mudras"][0]["mudra"] == "Alapadmam"
    assert mapping["mudras"][0]["meaning"] == "Full-blown lotus"
    assert mapping["mudras"][0]["status"] == "mapped"


@pytest.mark.parametrize(
    "mutate, expected_code",
    [
        (lambda response: response["scenes"][1].update(evidence_text="Radha turns away shyly."), "UNSUPPORTED_STORY_EXTRACTION"),
        (lambda response: response["scenes"][0].update(characters=["Sita"]), "UNSUPPORTED_STORY_EXTRACTION"),
        (lambda response: response["scenes"][0].update(action_type="fly"), "INVALID_STORY_EXTRACTION"),
    ],
)
def test_unverifiable_or_out_of_order_extraction_is_rejected(
    monkeypatch, tmp_path, mutate, expected_code
):
    output = _scenes()
    mutate(output)
    _wire(monkeypatch, tmp_path, output)
    story = service.create_story(
        "Krishna enters the garden. Krishna offers a conch. Radha turns away shyly."
    )

    with pytest.raises(AppError) as error:
        service.generate_dance_plan(story["story_id"])

    assert error.value.code == expected_code
    assert service.get_story(story["story_id"])["dance_plan"] is None


def test_language_validation_and_repeated_generation_are_isolated(monkeypatch, tmp_path):
    provider = _wire(monkeypatch, tmp_path)
    with pytest.raises(AppError) as unsupported:
        service.create_story("A story.", language="French")
    assert unsupported.value.code == "UNSUPPORTED_STORY_LANGUAGE"

    provider.output = {
        "scenes": [{
            "evidence_text": "கிருஷ்ணன் தோட்டத்திற்குள் நுழைகிறார்.",
            "characters": ["கிருஷ்ணன்"],
            "action_type": "enter",
            "action_text": "நுழைகிறார்",
            "objects": [],
            "location": "தோட்டத்திற்குள்",
            "expressive_qualities": [],
        }]
    }
    tamil = service.create_story("கிருஷ்ணன் தோட்டத்திற்குள் நுழைகிறார்.", language="ta")
    first = service.generate_dance_plan(tamil["story_id"])
    second = service.generate_dance_plan(tamil["story_id"])
    provider.output = {
        "scenes": [{
            "evidence_text": "A separate story.",
            "characters": [],
            "action_type": "other",
            "action_text": "story",
            "objects": [],
            "location": "",
            "expressive_qualities": [],
        }]
    }
    english = service.create_story("A separate story.", language="en")
    english_plan = service.generate_dance_plan(english["story_id"])

    assert first["dance_plan"]["language"] == "ta"
    assert first["dance_plan"]["dance_plan_id"] == second["dance_plan"]["dance_plan_id"]
    assert first["dance_plan"]["choreography_id"] == second["dance_plan"]["choreography_id"]
    assert first["dance_plan"]["story_id"] != english_plan["dance_plan"]["story_id"]
    assert first["dance_plan"]["scenes"][0]["scene_id"] != english_plan["dance_plan"]["scenes"][0]["scene_id"]
    assert len(provider.requests) == 2


def test_empty_story_and_unknown_story_id_fail_explicitly(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    with pytest.raises(AppError) as empty:
        service.create_story("   ")
    assert empty.value.code == "EMPTY_STORY"
    with pytest.raises(AppError) as missing:
        service.get_story("11111111-1111-4111-8111-111111111111")
    assert missing.value.code == "STORY_NOT_FOUND"


def test_missing_gemini_provider_is_reported_without_fallback(monkeypatch, tmp_path):
    provider = _wire(monkeypatch, tmp_path)
    provider.available = False
    story = service.create_story("A story.")

    with pytest.raises(AppError) as error:
        service.generate_dance_plan(story["story_id"])

    assert error.value.code == "STORY_TO_DANCE_PROVIDER_UNAVAILABLE"
    assert service.get_story(story["story_id"])["dance_plan"] is None
