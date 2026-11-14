"""Procedural temporal dancer-avatar synthesis and MP4 rendering."""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.api.schemas.dance_generation import (
    DanceGeneratorOutput,
    GeneratorPoseFrame,
    GeneratorSceneResult,
    StoryDanceGenerationRequest,
)
from app.config import settings

logger = logging.getLogger(__name__)

_WIDTH = 640
_HEIGHT = 720
_BLENDER_WIDTH = 720
_BLENDER_HEIGHT = 810
_FPS = 20.0
_BACKGROUND = (249, 240, 216)
_INK = (57, 36, 30)
_SKIN = (177, 99, 63)
_SKIN_LIGHT = (211, 145, 101)
_HAIR = (42, 29, 27)
_SARI = (173, 47, 51)
_SARI_LIGHT = (218, 113, 58)
_GOLD = (202, 157, 73)
_BLOUSE = (40, 94, 82)
_PINK = (205, 100, 132)
_LOTUS_PINK = (203, 81, 135)
_LOTUS_LIGHT = (236, 145, 177)
_CONCH = (235, 222, 190)
_CONCH_SHADE = (155, 111, 71)
_FIVE_SCENE_FRAME_COUNTS = (100, 80, 100, 80, 120)
_SEVEN_SCENE_FRAME_COUNTS = (100, 80, 100, 100, 80, 100, 120)
_GENERIC_SCENE_FRAMES = int(_FPS * 4)


def _scene_concepts(scene: Any) -> list[str]:
    concepts: list[str] = []
    for item in getattr(scene, "movement_concept", []) or []:
        concept_name = getattr(item, "concept", None)
        if concept_name:
            concepts.append(str(concept_name))
    return concepts


def _scene_movement_sequence(scene: Any) -> list[str]:
    planned_sequence = getattr(scene, "visualization_sequence", None)
    if planned_sequence and any(
        (
            str(item).casefold().startswith("creative ")
            and str(item).casefold() != "creative story-action visualization"
        )
        or str(item).casefold() == "source-expression facial intent"
        for item in planned_sequence
    ):
        return [str(item) for item in planned_sequence]

    action_text = (getattr(scene, "action", "") or "").casefold()
    source_text = (getattr(scene, "source_text", "") or "").casefold()
    objects = " ".join(getattr(scene, "objects", []) or []).casefold()
    location = (getattr(scene, "location", "") or "").casefold()

    return _curated_scene_movement_sequence(
        action_text,
        source_text,
        objects,
        location,
    )


def _curated_scene_movement_sequence(
    action_text: str,
    source_text: str,
    objects: str,
    location: str,
) -> list[str]:
    if "turn" in action_text and ("conch" in objects or "conch" in source_text or "shanka" in objects or "shanka" in source_text):
        return ["turn_body_toward_conch", "perform_bhramari", "face_conch", "form_shanka", "hold_shanka"]
    if "turn" in action_text:
        if "anjali" in source_text or "hands" in objects or "palms" in objects:
            if "return" in action_text or "center" in source_text:
                return [
                    "perform_bhramari",
                    "complete_turn",
                    "walk_backward_or_return_to_center",
                    "face_forward",
                    "raise_hands",
                    "join_palms",
                    "hold_anjali",
                    "final_pose",
                ]
            return ["raise_hands", "join_palms", "hold_anjali", "head_bow", "return_head"]
        if "return" in action_text or "center" in source_text:
            return ["prepare_turn", "perform_bhramari", "return_to_center", "finish_pose"]
        return ["prepare_turn", "perform_bhramari", "return_to_center", "finish_pose"]
    if "enter" in action_text:
        return ["walk_forward", "face_direction", "form_alapadmam", "look_at_target"]
    if "open" in action_text and "hand" in action_text:
        return ["turn_head_toward_target", "raise_hands", "open_hands", "form_alapadmam", "hold_alapadmam", "look_at_target"]
    if "raise" in action_text and "hand" in action_text:
        return ["raise_hands", "join_palms", "hold_anjali", "head_bow", "return_head"]
    if "look" in action_text or "notice" in source_text or "notices" in source_text or "see" in source_text or "admiration" in source_text:
        if "conch" in objects or "conch" in source_text:
            return [
                "turn_head_toward_conch",
                "shift_body_attention",
                "gesture_toward_target",
                "prepare_shanka",
                "form_shanka",
                "hold_shanka",
            ]
        if "lotus" in objects or "lotus" in location:
            if "reach" in source_text or "gently" in source_text or "toward the lotus" in source_text:
                return [
                    "step_or_lean_forward",
                    "reach_forward",
                    "form_alapadmam",
                    "close_or_hold_lotus",
                    "bring_lotus_toward_body",
                    "look_at_target",
                    "admiration_pose",
                ]
            return ["reach_forward", "form_alapadmam", "hold_lotus", "look_at_target", "admiration"]
        return ["turn_head", "gesture_toward_target", "form_shanka", "hold_gesture"]
    if "conch" in objects or "conch" in source_text:
        if (
            "turn" in action_text
            and ("toward" in source_text or "shows" in source_text or "shanka" in source_text)
        ):
            return [
                "turn_body_toward_conch",
                "perform_bhramari",
                "face_conch",
                "form_shanka",
                "hold_shanka",
            ]
        if "gesture" in source_text or "point" in action_text:
            return ["turn_head", "gesture_toward_target", "form_shanka", "hold_gesture"]
        return ["turn_head", "gesture_toward_target", "form_shanka", "hold_gesture"]
    if "anjali" in source_text or "pray" in action_text:
        return ["raise_hands", "join_palms", "hold_anjali", "head_bow", "return_head"]
    if "lotus" in objects or "lotus" in source_text:
        return ["reach_forward", "form_alapadmam", "hold_lotus", "look_at_target", "admiration"]
    return ["walk_forward", "face_direction", "form_alapadmam", "look_at_target"]


def _scene_frame_count(scene: Any, scene_count: int) -> int:
    duration_seconds = getattr(scene, "duration_seconds", None)
    if isinstance(duration_seconds, (int, float)) and duration_seconds > 0:
        return max(1, round(float(duration_seconds) * _FPS))

    index = max(0, scene.scene_order - 1)
    counts_by_scene_number = {
        1: (100,),
        5: (100, 80, 100, 80, 120),
        7: (100, 80, 100, 100, 80, 100, 120),
    }
    if scene_count in counts_by_scene_number:
        sequence = counts_by_scene_number[scene_count]
        if index < len(sequence):
            return int(sequence[index])
    return int(_GENERIC_SCENE_FRAMES)


def _target_kinds(scene: Any) -> set[str]:
    objects = [str(item).casefold() for item in getattr(scene, "objects", []) or []]
    target_text = " ".join(objects + [getattr(scene, "location", "") or ""])
    kinds: set[str] = set()
    if any("lotus" in item for item in objects):
        kinds.add("lotus")
    if any("conch" in item for item in objects):
        kinds.add("conch")
    if any("hand" in item or "palm" in item for item in objects):
        kinds.add("hands")
    if any("garden" in item for item in objects + [target_text]):
        kinds.add("garden")
    intent = getattr(scene, "movement_intent", None)
    intent_target = None
    if intent is not None:
        if getattr(intent, "target", None):
            intent_target = str(intent.target)
        elif getattr(intent, "actions", None):
            for action in intent.actions:
                target = getattr(action, "target", None)
                if target:
                    intent_target = str(target)
                    break
    if intent_target:
        lowered = intent_target.casefold()
        if "lotus" in lowered:
            kinds.add("lotus")
        if "conch" in lowered:
            kinds.add("conch")
        if "hand" in lowered or "palm" in lowered:
            kinds.add("hands")
        if "garden" in lowered:
            kinds.add("garden")
    return kinds


def _intent_target(scene: Any) -> str | None:
    intent = getattr(scene, "movement_intent", None)
    actions = getattr(intent, "actions", None) or []
    if actions:
        targets = []
        for action in actions:
            target = getattr(action, "target", None)
            targets.append(str(target) if target else "—")
        if targets:
            return " → ".join(targets)
    target = getattr(intent, "target", None) if intent is not None else None
    return str(target) if target else None


def _expressive_state(scene: Any) -> str:
    text = " ".join(
        [getattr(scene, "source_text", "") or "", getattr(scene, "action", "") or ""]
    ).casefold()
    if "admiration" in text or "look" in text and "lotus" in text:
        return "admiration"
    if any(term in text for term in ("happiness", "happy", "joy", "gratitude", "grateful")):
        return "graceful"
    if "respectful" in text or "anjali" in text or "pray" in text:
        return "respectful"
    if "graceful" in text or "circular" in text or "return" in text and "turn" in text:
        return "graceful"
    if "conch" in text or "gesture" in text:
        return "attention"
    return "neutral"


def _pose_for_frame(
    scene: Any,
    local_frame: int,
    scene_count: int,
    render_props: set[str],
) -> dict[str, Any]:
    scene_text = f"{getattr(scene, 'source_text', '')} {getattr(scene, 'action', '')}".casefold()
    total_frames = _scene_frame_count(scene, scene_count)
    progress = 0.0 if total_frames <= 1 else local_frame / max(1, total_frames - 1)
    objects = [str(item).casefold() for item in getattr(scene, "objects", []) or []]
    target_kind = "lotus" if "lotus" in render_props else "conch" if "conch" in render_props else "hands" if "hands" in render_props else next(iter(sorted(render_props))) if render_props else "garden"
    target_kinds = sorted(render_props) if render_props else [target_kind]

    intent = getattr(scene, "movement_intent", None)
    movement_intent = intent.model_dump(mode="json") if hasattr(intent, "model_dump") else intent
    mudra = [item.mudra for item in getattr(scene, "mudra", []) or [] if getattr(item, "status", None) == "mapped" and getattr(item, "mudra", None)]
    direction = getattr(intent, "direction", None)
    if getattr(intent, "actions", None):
        directions = [str(action.direction) for action in intent.actions if getattr(action, "direction", None)]
        if directions:
            direction = " → ".join(directions)
    target = _intent_target(scene)

    if "raise" in scene_text and "hand" in scene_text:
        arm_pose = "anjali"
        arm_raise = 0.65
        arm_progress = min(1.0, 0.4 + progress * 0.8)
        head_turn = 0.0
        head_bow = 0.9 if progress < 0.6 else 0.35
        step_phase = 0.0
        x_offset = 0.0
        y_offset = 0.0
        rotation_degrees = 0.0
        gesture_phase = 1.0 - abs(0.5 - progress) * 2.0
    elif "lotus" in scene_text and ("look" in scene_text or "admiration" in scene_text):
        arm_pose = "lotus"
        arm_raise = 0.45 + progress * 0.4
        arm_progress = 0.6 + progress * 0.5
        head_turn = 0.2 if target_kind == "lotus" else 0.0
        head_bow = 0.3
        step_phase = math.pi * progress
        x_offset = 0.0
        y_offset = 0.0
        rotation_degrees = 0.0
        gesture_phase = 0.8 + 0.2 * math.sin(progress * math.pi * 2)
    elif "conch" in scene_text or "gesture" in scene_text:
        arm_pose = "shanka" if "shanka" in scene_text or "conch" in scene_text else "point"
        arm_raise = 0.55 + progress * 0.25
        arm_progress = 0.5 + progress * 0.5
        head_turn = 0.75 if target_kind == "conch" else 0.4
        head_bow = 0.1
        step_phase = math.pi * 0.5 + progress * math.pi
        if local_frame < 12:
            x_offset = 0.0
        elif local_frame >= total_frames - 3:
            x_offset = 0.0
        else:
            x_offset = -15.0 * (local_frame - 11) / max(1, total_frames - 12)
        y_offset = 0.0
        rotation_degrees = 0.0
        gesture_phase = 0.7 + 0.3 * progress
    elif "turn" in scene_text and "return" in scene_text:
        arm_pose = "point"
        arm_raise = 0.28
        arm_progress = 0.6
        head_turn = 0.2
        head_bow = 0.1
        step_phase = math.pi * progress
        if local_frame < 12:
            x_offset = 0.0
        elif local_frame < 20:
            x_offset = -36.0 - (local_frame - 12) * 4.8
        elif local_frame < 36:
            x_offset = -60.0 - (local_frame - 20) * 1.5
        else:
            x_offset = 0.0
        rotation_degrees = 360.0 if local_frame >= total_frames - 1 else 360.0 * min(1.0, max(0.0, (local_frame - 12) / max(1, total_frames - 12)))
        y_offset = 0.0
        gesture_phase = 0.5 + math.sin(progress * math.pi * 2) * 0.5
    elif "enter" in scene_text:
        arm_pose = "reach"
        arm_raise = 0.2 + progress * 0.4
        arm_progress = 0.3 + progress * 0.6
        head_turn = 0.25 if "lotus" in objects else 0.1
        head_bow = 0.0
        step_phase = progress * math.pi * 2
        x_offset = 0.0
        y_offset = 0.0
        rotation_degrees = 0.0
        gesture_phase = progress
    else:
        arm_pose = "reach"
        arm_raise = 0.3 + progress * 0.4
        arm_progress = 0.4 + progress * 0.5
        head_turn = 0.15
        head_bow = 0.1
        step_phase = progress * math.pi * 2
        x_offset = 0.0
        y_offset = 0.0
        rotation_degrees = 0.0
        gesture_phase = progress

    if local_frame >= max(0, total_frames - 3):
        x_offset = 0.0
        if "turn" in scene_text and "return" in scene_text:
            rotation_degrees = 360.0

    movement_sequence = _scene_movement_sequence(scene)
    movement_concepts = _scene_concepts(scene)
    source_provenance = [
        provenance.model_dump(mode="json") for provenance in getattr(scene, "source_provenance", []) or []
    ]
    scene_id = getattr(scene, "scene_id", None)
    pose_data = {
        "scene_id": scene_id,
        "scene_order": getattr(scene, "scene_order", scene_count),
        "target_kind": target_kind,
        "target_kinds": target_kinds,
        "movement_concepts": movement_concepts,
        "mapping_status": getattr(scene, "mapping_status", "review_required"),
        "candidate_adavu": None,
        "movement_intent": movement_intent,
        "movement_sequence": movement_sequence,
        "mudra": mudra,
        "target": target,
        "direction": direction,
        "transition": (
            "Ease into the scene from a settled stance, perform its ordered movement phases, "
            "and ease toward a finish pose."
        ),
        "expressive_state": _expressive_state(scene),
        "source_provenance": source_provenance,
        "x_offset": float(x_offset),
        "y_offset": float(y_offset),
        "rotation_degrees": float(rotation_degrees),
        "arm_pose": arm_pose,
        "arm_raise": float(arm_raise),
        "arm_progress": float(arm_progress),
        "gesture_phase": float(gesture_phase),
        "head_turn": float(head_turn),
        "head_bow": float(head_bow),
        "step_phase": float(step_phase),
        "scene_index": getattr(scene, "scene_order", 1) - 1,
        "progress": float(progress),
    }
    return pose_data


def _smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_background(image: Image.Image, scene_order: int, scene_count: int) -> None:
    draw = ImageDraw.Draw(image)
    for y in range(_HEIGHT):
        blend = y / _HEIGHT
        color = tuple(
            int(_BACKGROUND[index] * (1 - blend * 0.18) + (222, 200, 151)[index] * blend * 0.18)
            for index in range(3)
        )
        draw.line((0, y, _WIDTH, y), fill=color)

    draw.ellipse((32, 44, 118, 130), fill=(232, 184, 91), outline=(207, 150, 65), width=2)
    draw.rectangle((0, 514, _WIDTH, _HEIGHT), fill=(224, 202, 156))
    draw.ellipse((96, 489, 542, 576), fill=(216, 192, 143))

    for x, height, color in ((92, 90, (100, 128, 81)), (548, 115, (112, 133, 79))):
        draw.line((x, 500, x, 500 - height), fill=(112, 87, 58), width=11)
        for offset in (-42, -15, 18, 43):
            draw.ellipse(
                (x + offset - 31, 500 - height + abs(offset) // 2 - 34,
                 x + offset + 31, 500 - height + abs(offset) // 2 + 29),
                fill=color,
            )

    for index, x in enumerate((156, 496)):
        y = 525 + (index % 2) * 11
        draw.ellipse((x - 20, y - 8, x + 20, y + 8), fill=(93, 120, 71))
        draw.ellipse((x - 24, y - 15, x + 24, y + 1), outline=(246, 227, 181), width=3)
        draw.ellipse((x - 10, y - 13, x + 10, y + 5), fill=_PINK)
        draw.ellipse((x - 4, y - 10, x + 4, y - 2), fill=(247, 224, 161))

    draw.text((28, 24), "STORY TO MOVEMENT INTERPRETATION", fill=_INK, font=_font(17))
    draw.text(
        (_WIDTH - 28, 26),
        f"{scene_order:02d} / {scene_count:02d}",
        fill=_INK,
        font=_font(15),
        anchor="ra",
    )


def _draw_lotus(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0) -> None:
    draw.line((x, y + 15 * scale, x, y + 90 * scale), fill=(71, 111, 68), width=max(2, int(5 * scale)))
    draw.ellipse((x - 28 * scale, y + 62 * scale, x + 28 * scale, y + 76 * scale), fill=(81, 119, 69))
    for angle in (-72, -48, -24, 0, 24, 48, 72):
        radians = math.radians(angle - 90)
        tip_x = x + math.cos(radians) * 34 * scale
        tip_y = y + math.sin(radians) * 37 * scale
        draw.ellipse(
            (
                tip_x - 10 * scale,
                tip_y - 18 * scale,
                tip_x + 10 * scale,
                tip_y + 18 * scale,
            ),
            fill=_LOTUS_PINK if angle % 2 == 0 else _LOTUS_LIGHT,
            outline=(153, 63, 106),
            width=max(1, int(2 * scale)),
        )
    draw.ellipse(
        (x - 12 * scale, y - 9 * scale, x + 12 * scale, y + 15 * scale),
        fill=(244, 200, 108),
        outline=(181, 135, 65),
        width=max(1, int(2 * scale)),
    )
    draw.ellipse(
        (x - 5 * scale, y - 3 * scale, x + 5 * scale, y + 6 * scale),
        fill=(111, 71, 53),
    )


def _draw_conch(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0) -> None:
    shell = (
        x - 44 * scale,
        y - 31 * scale,
        x + 38 * scale,
        y + 31 * scale,
    )
    draw.ellipse(shell, fill=_CONCH, outline=_CONCH_SHADE, width=max(2, int(3 * scale)))
    draw.polygon(
        [
            (x + 12 * scale, y - 20 * scale),
            (x + 56 * scale, y),
            (x + 12 * scale, y + 20 * scale),
        ],
        fill=_CONCH,
        outline=_CONCH_SHADE,
    )
    for ridge in range(4):
        offset = ridge * 12 * scale
        draw.arc(
            (
                x - 35 * scale + offset,
                y - 25 * scale + offset * 0.18,
                x + 20 * scale + offset,
                y + 25 * scale - offset * 0.18,
            ),
            70,
            290,
            fill=_CONCH_SHADE,
            width=max(1, int(2 * scale)),
        )
    draw.ellipse(
        (x - 50 * scale, y - 9 * scale, x - 34 * scale, y + 9 * scale),
        fill=(109, 82, 59),
    )


def _draw_hand(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    shape: str,
    direction: int,
) -> None:
    palm = (x - 15, y - 15, x + 15, y + 17)
    draw.ellipse(palm, fill=_SKIN_LIGHT, outline=_SKIN, width=3)
    if shape == "anjali":
        for offset in (-7, 0, 7):
            draw.line(
                (x + offset, y + 8, x + offset, y - 26),
                fill=_SKIN_LIGHT,
                width=5,
            )
        draw.line((x - 12, y - 12, x, y - 18, x + 12, y - 12), fill=_SKIN, width=3)
    elif shape == "alapadmam":
        for index in range(5):
            angle = math.radians(-90 + (index - 2) * 34)
            tip_x = x + math.cos(angle) * 29
            tip_y = y + math.sin(angle) * 29
            draw.line((x, y - 4, tip_x, tip_y), fill=_SKIN_LIGHT, width=5)
            draw.ellipse((tip_x - 3, tip_y - 3, tip_x + 3, tip_y + 3), fill=_GOLD)
    elif shape == "shanka":
        draw.arc((x - 22, y - 23, x + 25, y + 20), start=190, end=520, fill=_SKIN, width=5)
        draw.arc((x - 12, y - 16, x + 15, y + 14), start=190, end=520, fill=_GOLD, width=2)
        draw.ellipse((x - 3, y - 4, x + 4, y + 4), fill=_GOLD)
    elif shape == "point":
        draw.line((x + direction * 2, y, x + direction * 39, y - 8), fill=_SKIN_LIGHT, width=6)
        draw.ellipse((x + direction * 35 - 3, y - 11, x + direction * 41, y - 5), fill=_SKIN)
        for offset in (-7, 0, 7):
            draw.line((x - direction * 6, y + offset, x + direction * 12, y + offset + 5), fill=_SKIN, width=3)
    else:
        for offset in (-8, 0, 8):
            draw.line((x + offset, y + 8, x + offset, y - 17), fill=_SKIN_LIGHT, width=4)


def _draw_dancer(
    image: Image.Image,
    *,
    x_offset: float,
    rotation_degrees: float,
    arm_pose: str,
    arm_raise: float,
    arm_progress: float,
    gesture_phase: float,
    head_turn: float,
    head_bow: float,
    expressive_state: str,
    step_phase: float,
    scene_index: int,
) -> None:
    draw = ImageDraw.Draw(image)
    center_x = _WIDTH / 2 + x_offset
    yaw = math.radians(rotation_degrees)
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)

    def project(x: float, y: float, z: float) -> tuple[float, float]:
        x_r = x * cos_y + z * sin_y
        z_r = -x * sin_y + z * cos_y
        scale = 255.0 / (4.4 + z_r)
        return center_x + x_r * scale, 540 - y * scale

    def draw_segment(start: tuple[float, float, float], end: tuple[float, float, float], *, width: int, fill: tuple[int, int, int], edge: tuple[int, int, int]) -> None:
        p0 = project(*start)
        p1 = project(*end)
        draw.line((p0, p1), fill=edge, width=width + 3)
        draw.line((p0, p1), fill=fill, width=width)

    draw.ellipse((center_x - 170, 540, center_x + 170, 610), fill=(48, 38, 25, 100))
    draw.ellipse((center_x - 150, 512, center_x + 150, 578), fill=(90, 84, 67, 80))

    left_hip = (-0.28, 0.95, 0.08)
    right_hip = (0.28, 0.95, 0.08)
    shoulder_left = (-0.58, 1.42, 0.18)
    shoulder_right = (0.58, 1.42, 0.18)

    draw.polygon(
        [
            project(*shoulder_left),
            project(*shoulder_right),
            project(*right_hip),
            project(*left_hip),
        ],
        fill=(30, 118, 98),
        outline=(197, 170, 101),
        width=3,
    )
    draw.polygon(
        [
            project(-0.18, 1.35, 0.18),
            project(0.18, 1.35, 0.18),
            project(0.34, 0.96, 0.1),
            project(-0.34, 0.96, 0.1),
        ],
        fill=(57, 138, 119),
        outline=(210, 173, 106),
        width=2,
    )

    if arm_pose == 'anjali':
        left_arm = [(-0.72, 1.36, 0.18), (-0.96, 0.92, 0.65), (-0.72, 0.52, 0.88)]
        right_arm = [(0.72, 1.36, 0.18), (0.96, 0.92, 0.65), (0.72, 0.52, 0.88)]
    elif arm_pose == 'lotus':
        left_arm = [(-0.72, 1.32, 0.26), (-1.06, 0.92, 0.82), (-0.80, 0.62, 0.96)]
        right_arm = [(0.72, 1.32, 0.26), (1.06, 0.92, 0.82), (0.80, 0.62, 0.96)]
    elif arm_pose == 'shanka':
        left_arm = [(-0.70, 1.28, 0.16), (-1.08, 0.94, 0.72), (-0.90, 0.62, 1.08)]
        right_arm = [(0.70, 1.28, 0.16), (1.18, 0.90, 0.52), (1.12, 0.50, 0.80)]
    elif arm_pose == 'point':
        left_arm = [(-0.70, 1.26, 0.20), (-0.98, 0.98, 0.68), (-0.72, 0.66, 0.96)]
        right_arm = [(0.70, 1.26, 0.20), (1.08, 0.94, 0.52), (1.20, 0.40, 0.82)]
    elif arm_pose in {'reach', 'flower_open'}:
        lift = 0.35 + arm_raise * 0.55
        left_arm = [(-0.65, 1.30, 0.25), (-1.04, 1.00, 0.90 + lift), (-0.80, 0.62, 1.10)]
        right_arm = [(0.65, 1.30, 0.25), (1.10, 1.00, 0.90 + lift), (1.18, 0.62, 0.90)]
    else:
        lift = 0.12 + arm_raise * 0.65
        left_arm = [(-0.64, 1.32, 0.30), (-0.98, 0.96, 0.42 + lift), (-0.76, 0.54, 0.72)]
        right_arm = [(0.64, 1.32, 0.30), (0.98, 0.96, 0.42 + lift), (0.76, 0.54, 0.72)]

    for start, mid, end in (left_arm, right_arm):
        draw_segment(start, mid, width=18, fill=(177, 108, 72), edge=(126, 79, 49))
        draw_segment(mid, end, width=14, fill=(201, 145, 108), edge=(125, 90, 62))

    left_knee = (-0.18, 0.42, 0.18 + 0.18 * math.sin(step_phase))
    right_knee = (0.18, 0.42, 0.18 + 0.18 * math.sin(step_phase + math.pi))
    left_ankle = (-0.18, 0.09, 0.22 + 0.20 * math.sin(step_phase))
    right_ankle = (0.18, 0.09, 0.22 + 0.20 * math.sin(step_phase + math.pi))
    draw_segment(left_hip, left_knee, width=18, fill=(136, 82, 57), edge=(104, 58, 37))
    draw_segment(left_knee, left_ankle, width=14, fill=(73, 45, 38), edge=(44, 26, 22))
    draw_segment(right_hip, right_knee, width=18, fill=(136, 82, 57), edge=(104, 58, 37))
    draw_segment(right_knee, right_ankle, width=14, fill=(73, 45, 38), edge=(44, 26, 22))

    hip_left_p = project(*left_hip)
    hip_right_p = project(*right_hip)
    draw.polygon(
        [
            project(-0.42, 1.03, 0.02),
            project(0.42, 1.03, 0.02),
            hip_right_p,
            hip_left_p,
        ],
        fill=(155, 48, 54),
        outline=(202, 160, 92),
        width=2,
    )

    neck = project(0.0, 1.58, 0.10)
    head_center = project(0.0, 1.80, 0.12)
    draw.ellipse(
        (head_center[0] - 42, head_center[1] - 42, head_center[0] + 42, head_center[1] + 42),
        fill=(213, 161, 125),
        outline=(118, 80, 55),
        width=3,
    )
    draw.arc(
        (head_center[0] - 34, head_center[1] - 34, head_center[0] + 34, head_center[1] + 34),
        180,
        360,
        fill=(48, 31, 31),
        width=10,
    )
    eye_shift = head_turn * 10
    eye_y = head_center[1] - 4 + head_bow * 8
    left_eye = (head_center[0] - 11 + eye_shift, eye_y)
    right_eye = (head_center[0] + 11 + eye_shift, eye_y)
    draw.ellipse((left_eye[0] - 3, left_eye[1] - 3, left_eye[0] + 3, left_eye[1] + 3), fill=(34, 24, 23))
    draw.ellipse((right_eye[0] - 3, right_eye[1] - 3, right_eye[0] + 3, right_eye[1] + 3), fill=(34, 24, 23))
    mouth_y = head_center[1] + 16
    draw.arc((head_center[0] - 18, mouth_y - 8, head_center[0] + 18, mouth_y + 8), 200, 340, fill=(119, 62, 48), width=3)
    draw.ellipse((neck[0] - 16, neck[1] - 16, neck[0] + 16, neck[1] + 16), fill=(200, 147, 106), outline=(125, 82, 48), width=2)

    left_elbow = project(*left_arm[1])
    right_elbow = project(*right_arm[1])
    draw.ellipse((left_elbow[0] - 14, left_elbow[1] - 14, left_elbow[0] + 14, left_elbow[1] + 14), fill=(204, 145, 109), outline=(116, 83, 62), width=2)
    draw.ellipse((right_elbow[0] - 14, right_elbow[1] - 14, right_elbow[0] + 14, right_elbow[1] + 14), fill=(204, 145, 109), outline=(116, 83, 62), width=2)

    hand_left = project(*left_arm[2])
    hand_right = project(*right_arm[2])
    draw.ellipse((hand_left[0] - 10, hand_left[1] - 10, hand_left[0] + 10, hand_left[1] + 10), fill=(208, 148, 106), outline=(128, 90, 60), width=2)
    draw.ellipse((hand_right[0] - 10, hand_right[1] - 10, hand_right[0] + 10, hand_right[1] + 10), fill=(208, 148, 106), outline=(128, 90, 60), width=2)

    if arm_pose == 'anjali':
        draw.line((hand_left[0] - 12, hand_left[1], hand_right[0] + 12, hand_right[1]), fill=(255, 216, 140), width=5)

    draw.ellipse((center_x - 96, 534, center_x + 96, 555), fill=(24, 26, 28, 90))
    draw.ellipse((center_x - 52, 552, center_x + 52, 570), fill=(17, 18, 20, 70))

def _render_frame(
    scene: Any,
    scene_index: int,
    scene_count: int,
    pose: dict[str, Any],
) -> np.ndarray:
    image = Image.new("RGBA", (_WIDTH, _HEIGHT), (*_BACKGROUND, 255))
    _draw_background(image, scene_index + 1, scene_count)
    target = pose["target_kind"]
    targets = set(pose["target_kinds"])
    draw = ImageDraw.Draw(image)
    if "lotus" in targets:
        _draw_lotus(draw, 535, 397, 0.9)
    if "conch" in targets:
        _draw_conch(draw, 522, 438, 0.88)
        if target == "conch" and pose["arm_pose"] in {"point", "shanka"}:
            draw.line((455, 252, 503, 389), fill=(188, 147, 103), width=2)
            draw.polygon([(503, 389), (494, 377), (507, 378)], fill=(188, 147, 103))

    avatar_layer = Image.new("RGBA", (_WIDTH, _HEIGHT), (0, 0, 0, 0))
    _draw_dancer(
        avatar_layer,
        x_offset=pose["x_offset"],
        rotation_degrees=pose["rotation_degrees"],
        arm_pose=pose["arm_pose"],
        arm_raise=pose["arm_raise"],
        arm_progress=pose["arm_progress"],
        gesture_phase=pose["gesture_phase"],
        head_turn=pose["head_turn"],
        head_bow=pose["head_bow"],
        expressive_state=pose["expressive_state"],
        step_phase=pose["step_phase"],
        scene_index=scene_index,
    )

    angle = math.radians(pose["rotation_degrees"])
    horizontal_scale = max(0.12, abs(math.cos(angle)))
    target_width = max(1, int(_WIDTH * horizontal_scale))
    transformed = avatar_layer.resize(
        (target_width, _HEIGHT),
        Image.Resampling.LANCZOS,
    )
    if math.cos(angle) < 0:
        transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    image.alpha_composite(
        transformed,
        dest=(int((_WIDTH - target_width) / 2), int(pose["y_offset"])),
    )

    draw = ImageDraw.Draw(image)
    if "lotus" in targets and pose["arm_pose"] == "lotus" and pose["progress"] >= 0.52:
        _draw_lotus(draw, 372 + pose["x_offset"], 282 + pose["y_offset"], 0.36)
    title = scene.source_text.strip().replace("\n", " ")
    if len(title) > 78:
        title = title[:75].rstrip() + "..."
    draw.rounded_rectangle((25, 594, 615, 690), radius=16, fill=(255, 251, 239), outline=(201, 173, 122), width=2)
    draw.text((43, 603), f"Scene {scene_index + 1}: {title}", fill=_INK, font=_font(16))
    concepts = _scene_concepts(scene)
    annotation = (
        "Procedural illustration · Source-supported concept: " + " / ".join(concepts)
        if concepts
        else "Procedural story-action visualization · non-canonical"
    )
    draw.text((43, 633), annotation[:84], fill=(104, 78, 56), font=_font(14))
    actions = scene.movement_intent.actions
    action_label = " + ".join(action.action for action in actions) or scene.movement_intent.action
    target_label = " + ".join(
        action.target for action in actions if action.target
    ) or "none"
    direction_label = " + ".join(
        action.direction for action in actions if action.direction
    ) or "review required"
    draw.text(
        (43, 660),
        f"Action: {action_label[:24]} | Target: {target_label[:18]} | Direction: {direction_label[:22]}",
        fill=(104, 78, 56),
        font=_font(12),
    )

    small = image.convert("RGB").resize(
        (_WIDTH, _HEIGHT),
        Image.Resampling.LANCZOS,
    )
    return cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2BGR)


def _candidate_rigged_dancer_assets() -> list[Path]:
    project_root = Path(__file__).resolve().parents[3]
    paths: list[Path] = []

    if settings.rigged_dancer_asset_path is not None:
        paths.append(settings.rigged_dancer_asset_path)

    env_names = (
        "RIGGED_DANCER_ASSET_PATH",
        "HI_NATYAVERSE_RIGGED_DANCER_ASSET_PATH",
        "DANCER_ASSET_PATH",
    )
    for name in env_names:
        value = os.getenv(name, "").strip()
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        paths.append(candidate)

    for root in (
        project_root / "assets",
        project_root / "backend" / "assets",
        project_root / "backend" / "app" / "assets",
        project_root / "backend" / "models",
        project_root / "media",
    ):
        if root.exists():
            for pattern in ("**/*.glb", "**/*.gltf", "**/*.fbx", "**/*.dae"):
                paths.extend(root.glob(pattern))

    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() in {".glb", ".gltf", ".fbx", ".dae"} and path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def resolve_rigged_dancer_asset_path() -> Path | None:
    assets = _candidate_rigged_dancer_assets()
    return assets[0] if assets else None


def _blender_executable() -> str | None:
    env_override = os.getenv("BLENDER_PATH", "").strip()
    if env_override:
        candidate = Path(env_override).expanduser()
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    project_root = Path(__file__).resolve().parents[3]
    candidates = [
        project_root / "tools" / "blender-3.6.5-windows-x64" / "blender.exe",
        project_root / "tools" / "blender" / "blender.exe",
        Path("blender.exe"),
        Path("blender"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which("blender")


def _process_output_text(output: str | bytes | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def _save_blender_diagnostics(
    output_dir: Path,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> tuple[Path | None, Path | None]:
    paths: list[Path | None] = []
    for stream_name, output in (("stdout", stdout), ("stderr", stderr)):
        path = output_dir / f"blender.{stream_name}.log"
        try:
            path.write_text(_process_output_text(output), encoding="utf-8")
        except OSError:
            logger.exception("Could not save Blender %s diagnostics to %s.", stream_name, path)
            paths.append(None)
        else:
            paths.append(path)
    return paths[0], paths[1]


def _character_asset_path() -> Path:
    asset_path = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "innerscene-female-base-cc0.glb"
    )
    if not asset_path.is_file():
        raise FileNotFoundError(
            f"The CC0 rigged dancer base mesh is unavailable: {asset_path}"
        )
    return asset_path


def _build_blender_animation_script(
    request: StoryDanceGenerationRequest,
    frame_dir: Path,
) -> Path:
    character_asset_path = _character_asset_path()
    manifest_path = request.output_directory / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generation_id": request.generation_id,
                "story_id": request.story_id,
                "dance_plan_id": request.dance_plan_id,
                "choreography_id": request.choreography_id,
                "fps": _FPS,
                "width": _BLENDER_WIDTH,
                "height": _BLENDER_HEIGHT,
                "character_asset_path": str(character_asset_path),
                "frame_count": sum(
                    _scene_frame_count(scene, len(request.scenes)) for scene in request.scenes
                ),
                "scenes": [
                    {
                        "scene_id": scene.scene_id,
                        "scene_order": scene.scene_order,
                        "source_text": scene.source_text,
                        "action": scene.action,
                        "movement_intent": scene.movement_intent.model_dump(mode="json"),
                        "objects": scene.objects,
                        "mudra": [item.model_dump(mode="json") for item in scene.mudra],
                        "bhava": [item.model_dump(mode="json") for item in scene.bhava],
                        "movement_concepts": [
                            item.model_dump(mode="json") for item in scene.movement_concept
                        ],
                        "visualization_sequence": scene.visualization_sequence,
                        "frame_count": _scene_frame_count(scene, len(request.scenes)),
                        "count": _scene_frame_count(scene, len(request.scenes)),
                    }
                    for scene in request.scenes
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    script_path = request.output_directory / "blender_rigged_dancer.blender-script"
    script_path.write_text(
        """
import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Matrix
from mathutils import Vector

manifest = json.loads(Path(os.environ['HI_NATYA_RENDER_MANIFEST']).read_text(encoding='utf-8'))
frame_dir = Path(os.environ['HI_NATYA_FRAME_DIR'])
frame_dir.mkdir(parents=True, exist_ok=True)

for block in list(bpy.data.objects):
    bpy.data.objects.remove(block, do_unlink=True)
for block in list(bpy.data.meshes):
    bpy.data.meshes.remove(block, do_unlink=True)
for block in list(bpy.data.materials):
    bpy.data.materials.remove(block, do_unlink=True)
for block in list(bpy.data.armatures):
    bpy.data.armatures.remove(block, do_unlink=True)
for block in list(bpy.data.cameras):
    bpy.data.cameras.remove(block, do_unlink=True)
for block in list(bpy.data.lights):
    bpy.data.lights.remove(block, do_unlink=True)

scene = bpy.context.scene
scene.render.resolution_x = int(manifest['width'])
scene.render.resolution_y = int(manifest['height'])
scene.render.film_transparent = False
scene.render.fps = 20
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(frame_dir / 'frame_')
scene.frame_start = 1
scene.frame_end = int(manifest['frame_count'])
scene.render.resolution_percentage = 100
scene.render.image_settings.color_mode = 'RGB'
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.taa_render_samples = 16
scene.eevee.use_gtao = True
scene.eevee.gtao_distance = 2.2
scene.eevee.gtao_factor = 1.35
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'Medium High Contrast'
scene.view_settings.exposure = -0.15
scene.view_settings.gamma = 1
scene.world.use_nodes = True
world_background = scene.world.node_tree.nodes.get('Background')
world_background.inputs['Color'].default_value = (0.19, 0.12, 0.10, 1)
world_background.inputs['Strength'].default_value = 0.28

def add_area_light(name, location, energy, color, size, target):
    from mathutils import Vector

    bpy.ops.object.light_add(type='AREA', location=location)
    area = bpy.context.object
    area.name = name
    area.data.energy = energy
    area.data.color = color
    area.data.shape = 'DISK'
    area.data.size = size
    direction = Vector(target) - area.location
    area.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return area

key_light = add_area_light('Warm temple key', (-3.5, -4.0, 5.2), 850, (1.0, 0.78, 0.52), 4.0, (0, 0, 1))
fill_light = add_area_light('Soft frontal fill', (3.4, -3.2, 3.4), 480, (0.62, 0.77, 1.0), 3.8, (0, 0, 1))
rim_light = add_area_light('Golden stage rim', (0.0, 2.1, 4.8), 1050, (1.0, 0.48, 0.20), 3.0, (0, 0, 1))
bloom_light = add_area_light('Divine appearance glow', (0.0, -1.1, 4.6), 15, (1.0, 0.78, 0.42), 2.5, (0, 0, 1.5))

bpy.ops.object.camera_add(location=(0, -8.2, 0.72))
camera = bpy.context.object
camera.rotation_euler = (math.radians(89), 0, 0)
camera.location.y = -10.5
camera.data.lens = 48
camera.data.sensor_width = 36
scene.camera = camera

arm_data = bpy.data.armatures.new('DancerArmature')
arm_obj = bpy.data.objects.new('DancerRig', arm_data)
bpy.context.collection.objects.link(arm_obj)
arm_obj.location = (0, 0, 0)
bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.mode_set(mode='EDIT')

edit = arm_obj.data.edit_bones
bones = {}

def add_bone(name, head, tail, parent=None):
    bone = edit.new(name)
    bone.head = head
    bone.tail = tail
    bone.roll = 0.0
    if parent:
        bone.parent = bones[parent]
    bones[name] = bone

add_bone('root', (0.0, 0.0, 0.0), (0.0, 0.0, 0.70), None)
add_bone('pelvis', (0.0, 0.0, 0.70), (0.0, 0.0, 1.10), 'root')
add_bone('spine', (0.0, 0.0, 1.10), (0.0, 0.0, 1.75), 'pelvis')
add_bone('chest', (0.0, 0.0, 1.75), (0.0, 0.0, 2.28), 'spine')
add_bone('neck', (0.0, 0.0, 2.28), (0.0, 0.0, 2.58), 'chest')
add_bone('head', (0.0, 0.0, 2.58), (0.0, 0.0, 3.15), 'neck')
add_bone('shoulder_l', (-0.22, 0.0, 2.10), (-0.75, 0.0, 2.12), 'chest')
add_bone('upper_arm_l', (-0.75, 0.0, 2.12), (-1.30, 0.0, 1.80), 'shoulder_l')
add_bone('forearm_l', (-1.30, 0.0, 1.80), (-1.75, 0.0, 1.10), 'upper_arm_l')
add_bone('hand_l', (-1.75, 0.0, 1.10), (-1.95, 0.0, 0.62), 'forearm_l')
add_bone('shoulder_r', (0.22, 0.0, 2.10), (0.75, 0.0, 2.12), 'chest')
add_bone('upper_arm_r', (0.75, 0.0, 2.12), (1.30, 0.0, 1.80), 'shoulder_r')
add_bone('forearm_r', (1.30, 0.0, 1.80), (1.75, 0.0, 1.10), 'upper_arm_r')
add_bone('hand_r', (1.75, 0.0, 1.10), (1.95, 0.0, 0.62), 'forearm_r')
add_bone('thigh_l', (-0.22, 0.0, 0.70), (-0.80, 0.0, -0.15), 'pelvis')
add_bone('shin_l', (-0.80, 0.0, -0.15), (-0.58, 0.0, -1.55), 'thigh_l')
add_bone('foot_l', (-0.58, 0.0, -1.55), (-0.82, -0.18, -1.95), 'shin_l')
add_bone('thigh_r', (0.22, 0.0, 0.70), (0.80, 0.0, -0.15), 'pelvis')
add_bone('shin_r', (0.80, 0.0, -0.15), (0.58, 0.0, -1.55), 'thigh_r')
add_bone('foot_r', (0.58, 0.0, -1.55), (0.82, -0.18, -1.95), 'shin_r')

bpy.ops.object.mode_set(mode='OBJECT')

skin = bpy.data.materials.new(name='Skin')
skin.use_nodes = True
nodes = skin.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.64, 0.34, 0.21, 1.0)
bsdf.inputs['Roughness'].default_value = 0.72

sari = bpy.data.materials.new(name='Sari')
sari.use_nodes = True
nodes = sari.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.20, 0.012, 0.03, 1.0)
bsdf.inputs['Metallic'].default_value = 0.0
bsdf.inputs['Roughness'].default_value = 0.78
bsdf.inputs['Sheen'].default_value = 0.22

blouse = bpy.data.materials.new(name='Blouse')
blouse.use_nodes = True
nodes = blouse.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.012, 0.12, 0.065, 1.0)
bsdf.inputs['Metallic'].default_value = 0.02
bsdf.inputs['Roughness'].default_value = 0.68
bsdf.inputs['Sheen'].default_value = 0.16

for fabric in (sari, blouse):
    fabric_nodes = fabric.node_tree.nodes
    fabric_links = fabric.node_tree.links
    fabric_bsdf = fabric_nodes.get('Principled BSDF')
    weave = fabric_nodes.new('ShaderNodeTexNoise')
    weave.inputs['Scale'].default_value = 155
    weave.inputs['Detail'].default_value = 2
    weave.inputs['Roughness'].default_value = 0.72
    weave_bump = fabric_nodes.new('ShaderNodeBump')
    weave_bump.inputs['Strength'].default_value = 0.055
    weave_bump.inputs['Distance'].default_value = 0.012
    fabric_links.new(weave.outputs['Fac'], weave_bump.inputs['Height'])
    fabric_links.new(weave_bump.outputs['Normal'], fabric_bsdf.inputs['Normal'])

gold = bpy.data.materials.new(name='Gold')
gold.use_nodes = True
nodes = gold.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.84, 0.70, 0.25, 1.0)
bsdf.inputs['Metallic'].default_value = 0.9
bsdf.inputs['Roughness'].default_value = 0.16

hair = bpy.data.materials.new(name='Hair')
hair.use_nodes = True
nodes = hair.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.17, 0.12, 0.10, 1.0)

lotus = bpy.data.materials.new(name='Lotus')
lotus.use_nodes = True
nodes = lotus.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.78, 0.34, 0.52, 1.0)

body_parts = []
skin_mesh_parts = []

def attach_to_bone(obj, bone_name):
    bpy.context.view_layer.update()
    world_matrix = obj.matrix_world.copy()
    obj.parent = arm_obj
    obj.parent_type = 'BONE'
    obj.parent_bone = bone_name
    bpy.context.view_layer.update()
    obj.matrix_world = world_matrix

def add_mesh(name, primitive, loc, scale, material, parent_bone=None):
    if primitive == 'uv_sphere':
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=loc, segments=24, ring_count=16)
    elif primitive == 'cylinder':
        bpy.ops.mesh.primitive_cylinder_add(vertices=18, radius=1.0, depth=1.0, location=loc)
    elif primitive == 'cone':
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.0, radius2=0.0, depth=1.0, location=loc)
    elif primitive == 'cube':
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    if obj.data:
        obj.data.materials.append(material)
    if parent_bone:
        attach_to_bone(obj, parent_bone)
    if obj.type == 'MESH':
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    body_parts.append(obj)

def add_segment(name, start, end, radius, material, parent_bone):
    from mathutils import Vector

    start_point = Vector(start)
    end_point = Vector(end)
    direction = end_point - start_point
    midpoint = (start_point + end_point) * 0.5
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=1.0, location=midpoint, segments=32, ring_count=20
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = (radius, radius, direction.length * 0.62)
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = direction.to_track_quat('Z', 'Y')
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if parent_bone:
        attach_to_bone(obj, parent_bone)
    body_parts.append(obj)

def add_fused_sphere(name, location, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=1.0, location=location, segments=32, ring_count=24
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    skin_mesh_parts.append(obj)
    body_parts.append(obj)

def add_fused_segment(name, start, end, radius, material):
    add_segment(name, start, end, radius, material, None)
    skin_mesh_parts.append(body_parts[-1])

def fuse_weighted_body():
    bpy.ops.object.select_all(action='DESELECT')
    for obj in skin_mesh_parts:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    body_parts[:] = [obj for obj in body_parts if obj not in skin_mesh_parts]
    bpy.context.view_layer.objects.active = skin_mesh_parts[0]
    bpy.ops.object.join()
    body = bpy.context.object
    body.name = 'UnifiedSmoothDancerBody'
    remesh = body.modifiers.new('AnatomicalSurfaceFusion', 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = 0.035
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    smooth = body.modifiers.new('AnatomicalSmoothing', 'SMOOTH')
    smooth.factor = 1.15
    smooth.iterations = 4
    bpy.ops.object.modifier_apply(modifier=smooth.name)

    bones = [bone for bone in arm_obj.data.bones if bone.name != 'root']
    groups = {bone.name: body.vertex_groups.new(name=bone.name) for bone in bones}
    for vertex in body.data.vertices:
        closest = []
        for bone in bones:
            start = bone.head_local
            direction = bone.tail_local - start
            if direction.length_squared == 0:
                continue
            fraction = max(0.0, min(1.0, (vertex.co - start).dot(direction) / direction.length_squared))
            distance = (vertex.co - (start + direction * fraction)).length
            closest.append((distance, bone.name))
        closest.sort(key=lambda item: item[0])
        candidates = closest[:2]
        weights = [1.0 / max(0.02, distance + 0.06) ** 3 for distance, _ in candidates]
        total = sum(weights)
        for (_, bone_name), weight in zip(candidates, weights):
            groups[bone_name].add([vertex.index], weight / total, 'REPLACE')
    armature = body.modifiers.new('DancerArmatureDeformation', 'ARMATURE')
    armature.object = arm_obj
    body_parts.append(body)
    skin_mesh_parts.clear()

def add_front_detail(name, location, scale, material, bone_name):
    add_mesh(name, 'uv_sphere', location, scale, material, bone_name)

def add_torus(name, location, major_radius, minor_radius, material, bone_name=None):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=32,
        minor_segments=10,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler[0] = math.radians(90)
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if bone_name:
        attach_to_bone(obj, bone_name)
    body_parts.append(obj)

def add_skirt():
    vertices = []
    faces = []
    segments = 96
    height_levels = [-0.85, -0.65, -0.30, 0.10, 0.88]
    radii = [0.66, 0.62, 0.52, 0.37, 0.29]
    rings = len(height_levels)
    for height, radius in zip(height_levels, radii):
        z = -0.03 + height
        for index in range(segments):
            angle = 2 * math.pi * index / segments
            pleat = 1.0 + 0.045 * math.cos(20 * angle)
            vertices.append(
                (radius * pleat * math.cos(angle), radius * pleat * math.sin(angle), z)
            )
    for ring in range(rings - 1):
        for index in range(segments):
            current = ring * segments + index
            next_index = ring * segments + (index + 1) % segments
            faces.append((current, next_index, next_index + segments, current + segments))
    mesh = bpy.data.meshes.new('PleatedSariSkirtMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(sari)
    mesh.materials.append(gold)
    skirt = bpy.data.objects.new('PleatedSariSkirt', mesh)
    bpy.context.collection.objects.link(skirt)
    skirt.location = (0.0, 0.0, 0.55)
    attach_to_bone(skirt, 'pelvis')
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    body_parts.append(skirt)

def add_tailored_blouse():
    vertices = []
    faces = []
    profiles = (
        (1.22, 0.27, 0.20),
        (1.34, 0.28, 0.22),
        (1.50, 0.27, 0.21),
        (1.68, 0.30, 0.22),
        (1.84, 0.34, 0.22),
        (1.98, 0.37, 0.20),
        (2.10, 0.34, 0.18),
        (2.20, 0.26, 0.15),
    )
    ring_count = 32
    for z, width, depth in profiles:
        for index in range(ring_count):
            angle = 2.0 * math.pi * index / ring_count
            vertices.append((width * math.cos(angle), depth * math.sin(angle), z))
    for ring in range(len(profiles) - 1):
        for index in range(ring_count):
            current = ring * ring_count + index
            next_index = ring * ring_count + (index + 1) % ring_count
            faces.append((current, next_index, next_index + ring_count, current + ring_count))
    mesh = bpy.data.meshes.new('TailoredBlouseMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(blouse)
    garment = bpy.data.objects.new('TailoredBharatanatyamBlouse', mesh)
    bpy.context.collection.objects.link(garment)
    attach_to_bone(garment, 'chest')
    garment.modifiers.new('BlouseFabric', 'SOLIDIFY').thickness = 0.025
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    body_parts.append(garment)
    for sign in (-1, 1):
        add_segment(
            'BlouseSleeve',
            (sign * 0.36, 0.0, 2.14),
            (sign * 0.76, 0.0, 2.08),
            0.145,
            blouse,
            'chest',
        )
        add_torus('SleeveGoldBorder', (sign * 0.75, 0.0, 2.08), 0.14, 0.018, gold, 'chest')
    panel_vertices = []
    panel_faces = []
    panel_rows = (
        (1.24, 0.27, -0.34),
        (1.42, 0.29, -0.35),
        (1.62, 0.30, -0.36),
        (1.82, 0.34, -0.36),
        (1.98, 0.35, -0.34),
        (2.12, 0.31, -0.30),
    )
    for z, half_width, front_y in panel_rows:
        panel_vertices.extend(((-half_width, front_y, z), (half_width, front_y, z)))
    for row in range(len(panel_rows) - 1):
        first = row * 2
        panel_faces.append((first, first + 1, first + 3, first + 2))
    panel_mesh = bpy.data.meshes.new('BlouseFrontPanelMesh')
    panel_mesh.from_pydata(panel_vertices, [], panel_faces)
    panel_mesh.materials.append(blouse)
    panel = bpy.data.objects.new('VisibleBlouseFrontPanel', panel_mesh)
    bpy.context.collection.objects.link(panel)
    attach_to_bone(panel, 'chest')
    panel.modifiers.new('FrontPanelFabric', 'SOLIDIFY').thickness = 0.035
    body_parts.append(panel)
    add_segment('GoldBlouseHem', (-0.28, -0.375, 1.28), (0.28, -0.375, 1.28), 0.018, gold, 'chest')

def add_fan_panel():
    vertices = []
    faces = []
    columns = 16
    z_levels = [1.34, 1.05, 0.75, 0.45, 0.08]
    half_widths = [0.10, 0.16, 0.28, 0.46, 0.62]
    for row, (z, half_width) in enumerate(zip(z_levels, half_widths)):
        for column in range(columns + 1):
            ratio = column / columns * 2 - 1
            fold = 0.035 if column % 2 == 0 else 0.0
            vertices.append((half_width * ratio, -0.34 - fold, z))
    for row in range(len(z_levels) - 1):
        for column in range(columns):
            first = row * (columns + 1) + column
            faces.append((first, first + 1, first + columns + 2, first + columns + 1))
    mesh = bpy.data.meshes.new('PleatedFanMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(sari)
    panel = bpy.data.objects.new('BharatanatyamFrontFan', mesh)
    bpy.context.collection.objects.link(panel)
    attach_to_bone(panel, 'pelvis')
    panel.modifiers.new('FabricThickness', 'SOLIDIFY').thickness = 0.035
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    body_parts.append(panel)
    add_segment('FanGoldHem', (-0.62, -0.40, 0.08), (0.62, -0.40, 0.08), 0.025, gold, 'pelvis')
    for index in range(-3, 4):
        ratio = index / 4
        add_segment(
            'FanPleatTrim',
            (0.10 * ratio, -0.41, 1.28),
            (0.58 * ratio, -0.41, 0.10),
            0.012,
            gold,
            'pelvis',
        )

add_fused_sphere('Head', (0.0, 0.0, 2.85), (0.29, 0.26, 0.34), skin)
add_mesh('HairCap', 'uv_sphere', (0.0, 0.045, 3.05), (0.30, 0.28, 0.20), hair, 'head')
add_mesh('HairBun', 'uv_sphere', (0.0, 0.28, 3.06), (0.16, 0.15, 0.16), hair, 'head')
add_fused_sphere('Neck', (0.0, 0.0, 2.45), (0.15, 0.14, 0.24), skin)
add_fused_sphere('Torso', (0.0, 0.0, 1.82), (0.34, 0.25, 0.66), skin)
add_mesh('Waist', 'uv_sphere', (0.0, 0.0, 1.26), (0.30, 0.23, 0.22), blouse, 'pelvis')
add_mesh('HipDrape', 'uv_sphere', (0.0, 0.0, 0.97), (0.46, 0.29, 0.23), sari, 'pelvis')
add_fan_panel()
add_fused_segment('UpperArmL', (-0.48, 0.0, 2.17), (-1.30, 0.0, 1.80), 0.13, skin)
add_fused_segment('LowerArmL', (-1.30, 0.0, 1.80), (-1.88, 0.0, 1.02), 0.105, skin)
add_fused_segment('UpperArmR', (0.48, 0.0, 2.17), (1.30, 0.0, 1.80), 0.13, skin)
add_fused_segment('LowerArmR', (1.30, 0.0, 1.80), (1.88, 0.0, 1.02), 0.105, skin)
add_segment('ThighL', (-0.22, 0.0, 0.70), (-0.80, 0.0, -0.15), 0.18, sari, 'thigh_l')
add_segment('ShinL', (-0.80, 0.0, -0.15), (-0.58, 0.0, -1.55), 0.145, sari, 'shin_l')
add_fused_sphere('FootL', (-0.73, -0.05, -1.78), (0.16, 0.30, 0.13), skin)
add_segment('ThighR', (0.22, 0.0, 0.70), (0.80, 0.0, -0.15), 0.18, sari, 'thigh_r')
add_segment('ShinR', (0.80, 0.0, -0.15), (0.58, 0.0, -1.55), 0.145, sari, 'shin_r')
add_fused_sphere('FootR', (0.73, -0.05, -1.78), (0.16, 0.30, 0.13), skin)
fuse_weighted_body()

procedural_body = bpy.data.objects.get('UnifiedSmoothDancerBody')
if procedural_body is None:
    raise RuntimeError('The procedural body was not created before character replacement.')
body_parts[:] = [obj for obj in body_parts if obj != procedural_body]
bpy.data.objects.remove(procedural_body, do_unlink=True)

objects_before_import = set(bpy.data.objects)
character_asset = Path(manifest['character_asset_path'])
if not character_asset.is_file():
    raise RuntimeError(f'The licensed rigged character asset is missing: {character_asset}')
bpy.ops.import_scene.gltf(filepath=str(character_asset))
imported_objects = set(bpy.data.objects) - objects_before_import
realistic_armature = next(
    (obj for obj in imported_objects if obj.type == 'ARMATURE'),
    None,
)
realistic_mesh = max(
    (obj for obj in imported_objects if obj.type == 'MESH'),
    key=lambda obj: len(obj.data.vertices),
    default=None,
)
if realistic_armature is None or realistic_mesh is None:
    raise RuntimeError('The CC0 character asset did not provide its expected armature and body mesh.')
for imported_object in imported_objects:
    if imported_object.type == 'MESH' and imported_object != realistic_mesh:
        bpy.data.objects.remove(imported_object, do_unlink=True)

required_character_bones = {
    'root', 'pelvis.L', 'pelvis.R', 'spine05', 'spine04', 'spine03',
    'spine02', 'spine01', 'neck01', 'neck02', 'neck03', 'head',
    'clavicle.L', 'clavicle.R', 'shoulder01.L', 'shoulder01.R',
    'upperarm01.L', 'upperarm02.L', 'lowerarm01.L', 'lowerarm02.L',
    'wrist.L', 'upperarm01.R', 'upperarm02.R', 'lowerarm01.R',
    'lowerarm02.R', 'wrist.R', 'upperleg01.L', 'upperleg02.L',
    'lowerleg01.L', 'lowerleg02.L', 'foot.L', 'upperleg01.R',
    'upperleg02.R', 'lowerleg01.R', 'lowerleg02.R', 'foot.R',
}
missing_character_bones = required_character_bones.difference(
    realistic_armature.data.bones.keys()
)
if missing_character_bones:
    raise RuntimeError(
        'The CC0 character rig is missing required choreography bones: '
        + ', '.join(sorted(missing_character_bones))
    )

avatar_root = bpy.data.objects.new('RiggedHumanCharacterRoot', None)
bpy.context.collection.objects.link(avatar_root)
avatar_root.location = (0.0, 0.0, -1.95)
avatar_root.scale = (3.0, 3.0, 3.0)
for imported_object in (realistic_armature, realistic_mesh):
    imported_object.parent = avatar_root
    imported_object.matrix_parent_inverse = Matrix.Identity(4)

realistic_mesh.name = 'CC0HumanBaseBody'
skin_material = realistic_mesh.data.materials[0] if realistic_mesh.data.materials else None
if skin_material is None:
    skin_material = bpy.data.materials.new('ProceduralWarmSkin')
    realistic_mesh.data.materials.append(skin_material)
skin_material.name = 'ProceduralWarmSkin'
skin_material.use_nodes = True
skin_nodes = skin_material.node_tree.nodes
skin_links = skin_material.node_tree.links
skin_shader = skin_nodes.get('Principled BSDF')
if skin_shader is None:
    skin_shader = skin_nodes.new('ShaderNodeBsdfPrincipled')
output_node = next(
    (node for node in skin_nodes if node.type == 'OUTPUT_MATERIAL'),
    None,
)
if output_node is None:
    output_node = skin_nodes.new('ShaderNodeOutputMaterial')
skin_links.new(skin_shader.outputs['BSDF'], output_node.inputs['Surface'])
skin_shader.inputs['Base Color'].default_value = (0.30, 0.115, 0.065, 1.0)
skin_shader.inputs['Roughness'].default_value = 0.64
if 'Subsurface' in skin_shader.inputs:
    skin_shader.inputs['Subsurface'].default_value = 0.045
if 'Subsurface Radius' in skin_shader.inputs:
    skin_shader.inputs['Subsurface Radius'].default_value = (0.65, 0.30, 0.18)
skin_coordinates = skin_nodes.new('ShaderNodeTexCoord')
skin_tone_noise = skin_nodes.new('ShaderNodeTexNoise')
skin_tone_noise.inputs['Scale'].default_value = 5.5
skin_tone_noise.inputs['Detail'].default_value = 3.0
skin_tone_ramp = skin_nodes.new('ShaderNodeValToRGB')
skin_tone_ramp.color_ramp.elements[0].position = 0.18
skin_tone_ramp.color_ramp.elements[0].color = (0.27, 0.09, 0.05, 1.0)
skin_tone_ramp.color_ramp.elements[1].position = 0.82
skin_tone_ramp.color_ramp.elements[1].color = (0.35, 0.145, 0.08, 1.0)
skin_links.new(skin_coordinates.outputs['Generated'], skin_tone_noise.inputs['Vector'])
skin_links.new(skin_tone_noise.outputs['Fac'], skin_tone_ramp.inputs['Fac'])
skin_links.new(skin_tone_ramp.outputs['Color'], skin_shader.inputs['Base Color'])
skin_detail_noise = skin_nodes.new('ShaderNodeTexNoise')
skin_detail_noise.inputs['Scale'].default_value = 260
skin_detail_noise.inputs['Detail'].default_value = 2.0
skin_bump = skin_nodes.new('ShaderNodeBump')
skin_bump.inputs['Strength'].default_value = 0.045
skin_bump.inputs['Distance'].default_value = 0.001
skin_links.new(skin_coordinates.outputs['Generated'], skin_detail_noise.inputs['Vector'])
skin_links.new(skin_detail_noise.outputs['Fac'], skin_bump.inputs['Height'])
skin_links.new(skin_bump.outputs['Normal'], skin_shader.inputs['Normal'])
realistic_mesh.data.materials.clear()
realistic_mesh.data.materials.append(skin_material)
for modifier in realistic_mesh.modifiers:
    if modifier.type == 'ARMATURE':
        modifier.object = realistic_armature
body_parts.append(realistic_mesh)

character_bone_controls = {
    'spine05': 'pelvis',
    'spine03': 'spine',
    'spine01': 'chest',
    'neck02': 'neck',
    'head': 'head',
    'clavicle.L': 'shoulder_l',
    'upperarm01.L': 'upper_arm_l',
    'lowerarm01.L': 'forearm_l',
    'wrist.L': 'hand_l',
    'clavicle.R': 'shoulder_r',
    'upperarm01.R': 'upper_arm_r',
    'lowerarm01.R': 'forearm_r',
    'wrist.R': 'hand_r',
    'upperleg01.L': 'thigh_l',
    'lowerleg01.L': 'shin_l',
    'foot.L': 'foot_l',
    'upperleg01.R': 'thigh_r',
    'lowerleg01.R': 'shin_r',
    'foot.R': 'foot_r',
}
for character_bone_name, control_bone_name in character_bone_controls.items():
    rotation_constraint = realistic_armature.pose.bones[
        character_bone_name
    ].constraints.new('COPY_ROTATION')
    rotation_constraint.name = 'StoryDanceControl_' + control_bone_name
    rotation_constraint.target = arm_obj
    rotation_constraint.subtarget = control_bone_name
    rotation_constraint.owner_space = 'LOCAL'
    rotation_constraint.target_space = 'LOCAL'
    rotation_constraint.mix_mode = 'REPLACE'
    if character_bone_name in {'spine05', 'spine03', 'spine01', 'neck02', 'head'}:
        rotation_constraint.influence = 0.3

def bind_accessory_to_bone(obj, bone_name):
    group = obj.vertex_groups.new(name=bone_name)
    group.add(list(range(len(obj.data.vertices))), 1.0, 'REPLACE')
    modifier = obj.modifiers.new('AccessoryArmatureDeformation', 'ARMATURE')
    modifier.object = realistic_armature
    modifier.use_deform_preserve_volume = True

def add_root_sphere(name, location, scale, material, bone_name=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=1.0,
        location=(0.0, 0.0, 0.0),
        segments=24,
        ring_count=16,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.parent = avatar_root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.location = location
    obj.scale = scale
    if bone_name:
        bind_accessory_to_bone(obj, bone_name)
    body_parts.append(obj)
    return obj

def add_root_torus(name, location, major_radius, minor_radius, material, rotation=(0, 0, 0), bone_name=None):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=48,
        minor_segments=12,
        location=(0.0, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    obj.parent = avatar_root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.location = location
    obj.rotation_euler = rotation
    if bone_name:
        bind_accessory_to_bone(obj, bone_name)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    body_parts.append(obj)
    return obj

def add_root_curve(name, strands, radius, material):
    curve_data = bpy.data.curves.new(name, 'CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 12
    curve_data.bevel_depth = radius
    curve_data.bevel_resolution = 3
    for points in strands:
        spline = curve_data.splines.new('POLY')
        spline.points.add(len(points) - 1)
        for index, point in enumerate(points):
            spline.points[index].co = (*point, 1.0)
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj.parent = avatar_root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    body_parts.append(obj)
    return obj

def weight_cloth_to_bones(obj, bone_names):
    groups = {
        name: obj.vertex_groups.new(name=name)
        for name in bone_names
        if name in realistic_armature.data.bones
    }
    if not groups:
        raise RuntimeError(f'No compatible armature groups for costume mesh {obj.name}.')
    armature_inverse = realistic_armature.matrix_world.inverted()
    bone_segments = [
        (
            name,
            Vector(realistic_armature.data.bones[name].head_local),
            Vector(realistic_armature.data.bones[name].tail_local),
        )
        for name in groups
    ]
    for vertex in obj.data.vertices:
        point = armature_inverse @ (obj.matrix_world @ vertex.co)
        distances = []
        for name, start, end in bone_segments:
            direction = end - start
            length_squared = direction.length_squared
            progress = 0.0 if length_squared == 0 else max(
                0.0,
                min(1.0, (point - start).dot(direction) / length_squared),
            )
            distances.append(((point - (start + direction * progress)).length, name))
        closest = sorted(distances)[:3]
        weights = [1 / max(0.02, distance + 0.025) ** 4 for distance, _ in closest]
        total_weight = sum(weights)
        for (_, name), weight in zip(closest, weights):
            groups[name].add(
                [vertex.index],
                weight / total_weight,
                'REPLACE',
            )
    modifier = obj.modifiers.new('CostumeArmatureDeformation', 'ARMATURE')
    modifier.object = realistic_armature
    modifier.use_deform_preserve_volume = True
    for polygon in obj.data.polygons:
        polygon.use_smooth = True

def create_human_blouse():
    profile = (
        (0.815, 0.180, 0.115, -0.020),
        (0.880, 0.165, 0.112, -0.022),
        (0.940, 0.152, 0.105, -0.040),
        (1.000, 0.142, 0.100, -0.055),
        (1.060, 0.150, 0.110, -0.055),
        (1.120, 0.170, 0.120, -0.045),
        (1.180, 0.190, 0.120, -0.045),
        (1.230, 0.195, 0.110, -0.030),
        (1.260, 0.170, 0.100, -0.020),
        (1.295, 0.115, 0.080, -0.020),
    )
    rows = 49
    columns = 96
    vertices = []
    faces = []
    for row in range(rows):
        z = profile[0][0] + row / (rows - 1) * (profile[-1][0] - profile[0][0])
        lower = max((item for item in profile if item[0] <= z), default=profile[0])
        upper = min((item for item in profile if item[0] >= z), default=profile[-1])
        blend = (z - lower[0]) / max(1e-6, upper[0] - lower[0])
        width = lower[1] + blend * (upper[1] - lower[1])
        depth = lower[2] + blend * (upper[2] - lower[2])
        center_y = lower[3] + blend * (upper[3] - lower[3])
        for column in range(columns):
            angle = 2 * math.pi * column / columns
            vertices.append((
                math.cos(angle) * (width + 0.006),
                center_y + math.sin(angle) * (depth + 0.006),
                z,
            ))
    for row in range(rows - 1):
        for column in range(columns):
            start = row * columns + column
            next_column = row * columns + (column + 1) % columns
            faces.append((start, next_column, next_column + columns, start + columns))
    mesh = bpy.data.meshes.new('FittedHumanBlouseMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(blouse)
    garment = bpy.data.objects.new('FittedTealSilkBlouse', mesh)
    bpy.context.collection.objects.link(garment)
    garment.parent = avatar_root
    garment.matrix_parent_inverse = Matrix.Identity(4)
    garment.modifiers.new('SilkFabricThickness', 'SOLIDIFY').thickness = 0.004
    garment.modifiers.new('TailoredSurfaceSmoothing', 'SUBSURF').levels = 1
    weight_cloth_to_bones(
        garment,
        ('spine01', 'spine02', 'spine03', 'spine04', 'spine05', 'clavicle.L', 'clavicle.R'),
    )
    body_parts.append(garment)

def create_human_sleeve(side):
    shoulder = realistic_armature.data.bones[f'shoulder01.{side}']
    upper_arm = realistic_armature.data.bones[f'upperarm01.{side}']
    start = Vector(shoulder.head_local)
    end = Vector(upper_arm.tail_local)
    axis = (end - start).normalized()
    radial_a = axis.cross(Vector((0, 1, 0))).normalized()
    if radial_a.length < 1e-5:
        radial_a = axis.cross(Vector((0, 0, 1))).normalized()
    radial_b = axis.cross(radial_a).normalized()
    rows = 14
    columns = 36
    vertices = []
    faces = []
    for row in range(rows):
        progress = row / (rows - 1)
        center = start.lerp(end, progress)
        radius = 0.036 + 0.003 * math.sin(math.pi * progress)
        for column in range(columns):
            angle = 2 * math.pi * column / columns
            point = center + radius * (
                radial_a * math.cos(angle) + radial_b * math.sin(angle)
            )
            vertices.append(tuple(point))
    for row in range(rows - 1):
        for column in range(columns):
            start_index = row * columns + column
            next_column = row * columns + (column + 1) % columns
            faces.append((
                start_index,
                next_column,
                next_column + columns,
                start_index + columns,
            ))
    mesh = bpy.data.meshes.new(f'FittedBlouseSleeve_{side}')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(blouse)
    sleeve = bpy.data.objects.new(f'FittedBlouseSleeve_{side}', mesh)
    bpy.context.collection.objects.link(sleeve)
    sleeve.parent = avatar_root
    sleeve.matrix_parent_inverse = Matrix.Identity(4)
    sleeve.modifiers.new('SleeveFabricThickness', 'SOLIDIFY').thickness = 0.004
    weight_cloth_to_bones(
        sleeve,
        (f'shoulder01.{side}', f'upperarm01.{side}', f'upperarm02.{side}'),
    )
    body_parts.append(sleeve)

def create_human_legwear(side, start_bone_name, end_bone_name, bone_names, upper_radius, lower_radius):
    start = Vector(realistic_armature.data.bones[start_bone_name].head_local)
    end = Vector(realistic_armature.data.bones[end_bone_name].head_local)
    axis = (end - start).normalized()
    radial_a = axis.cross(Vector((0, 1, 0))).normalized()
    if radial_a.length < 1e-5:
        radial_a = axis.cross(Vector((0, 0, 1))).normalized()
    radial_b = axis.cross(radial_a).normalized()
    rows = 20
    columns = 40
    vertices = []
    faces = []
    for row in range(rows):
        progress = row / (rows - 1)
        center = start.lerp(end, progress)
        radius = upper_radius + progress * (lower_radius - upper_radius)
        for column in range(columns):
            angle = 2 * math.pi * column / columns
            point = center + radius * (
                radial_a * math.cos(angle) + radial_b * math.sin(angle)
            )
            vertices.append(tuple(point))
    for row in range(rows - 1):
        for column in range(columns):
            start_index = row * columns + column
            next_column = row * columns + (column + 1) % columns
            faces.append((
                start_index,
                next_column,
                next_column + columns,
                start_index + columns,
            ))
    mesh = bpy.data.meshes.new(f'ClassicalCostumeLegwear_{side}_{start_bone_name}')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(sari)
    garment = bpy.data.objects.new(
        f'MaroonClassicalLegwear_{side}_{start_bone_name}',
        mesh,
    )
    bpy.context.collection.objects.link(garment)
    garment.parent = avatar_root
    garment.matrix_parent_inverse = Matrix.Identity(4)
    garment.modifiers.new('LegwearSilkThickness', 'SOLIDIFY').thickness = 0.003
    weight_cloth_to_bones(garment, bone_names)
    body_parts.append(garment)

def add_character_face_detail(name, location, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=1.0,
        location=(0.0, 0.0, 0.0),
        segments=24,
        ring_count=16,
    )
    detail = bpy.context.object
    detail.name = name
    detail.data.materials.append(material)
    for polygon in detail.data.polygons:
        polygon.use_smooth = True
    detail.parent = avatar_root
    detail.matrix_parent_inverse = Matrix.Identity(4)
    detail.location = (location[0] / 3.0, location[1] / 3.0, (location[2] + 1.95) / 3.0)
    detail.scale = tuple(component / 3.0 for component in scale)
    body_parts.append(detail)
    return detail

eye_white = bpy.data.materials.new(name='NaturalEyeWhite')
eye_white.diffuse_color = (0.92, 0.87, 0.77, 1.0)
eye_iris = bpy.data.materials.new(name='DeepBrownIris')
eye_iris.diffuse_color = (0.075, 0.026, 0.014, 1.0)
eye_pupil = bpy.data.materials.new(name='EyePupil')
eye_pupil.diffuse_color = (0.012, 0.008, 0.006, 1.0)
face_makeup = bpy.data.materials.new(name='ClassicalEyeAndBindiMakeup')
face_makeup.diffuse_color = (0.13, 0.018, 0.025, 1.0)
lip_color = bpy.data.materials.new(name='LipColor')
lip_color.diffuse_color = (0.55, 0.13, 0.16, 1.0)
for eye_sign in (-1, 1):
    eye_x = eye_sign * 0.165
    add_character_face_detail(
        'HumanEyeSclera',
        (eye_x, -0.47, 2.70),
        (0.043, 0.020, 0.025),
        eye_white,
    )
    add_character_face_detail(
        'HumanEyeIris',
        (eye_x, -0.491, 2.70),
        (0.017, 0.009, 0.019),
        eye_iris,
    )
    add_character_face_detail(
        'HumanEyePupil',
        (eye_x, -0.500, 2.70),
        (0.008, 0.005, 0.012),
        eye_pupil,
    )
    add_character_face_detail(
        'ClassicalEyeLiner',
        (eye_x, -0.468, 2.736),
        (0.045, 0.008, 0.008),
        face_makeup,
    )
    add_character_face_detail(
        'ShapedEyebrow',
        (eye_x, -0.451, 2.754),
        (0.044, 0.008, 0.009),
        hair,
    )
add_character_face_detail(
    'Bindi',
    (0.0, -0.466, 2.847),
    (0.018, 0.008, 0.024),
    lip_color,
)

add_skirt()

obsolete_character_parts = {
    'Waist',
    'HipDrape',
    'ThighL',
    'ShinL',
    'FootL',
    'ThighR',
    'ShinR',
    'FootR',
    'VisibleBlouseFrontPanel',
    'TailoredBharatanatyamBlouse',
    'BlouseSleeve',
    'BlouseSleeve.001',
    'GoldBlouseHem',
}
replace_accessory_prefixes = (
    'HairCap',
    'HairBun',
    'LongClassicalBraid',
    'JasmineBraidFlower',
    'EarringHoop',
    'EarringDrop',
    'WristBangle',
    'WaistBelt',
    'GhungrooBell',
    'NecklaceBead',
    'WaistPendant',
    'TempleWaistChain',
    'KasuMalaNecklace',
    'Armlet',
    'TempleJewel',
    'FrontHairOrnament',
)
for obsolete_part in tuple(body_parts):
    if (
        obsolete_part.name in obsolete_character_parts
        or obsolete_part.name.startswith(replace_accessory_prefixes)
    ):
        body_parts.remove(obsolete_part)
        bpy.data.objects.remove(obsolete_part, do_unlink=True)

create_human_blouse()
create_human_sleeve('L')
create_human_sleeve('R')
for side in ('L', 'R'):
    create_human_legwear(
        side,
        f'upperleg01.{side}',
        f'lowerleg01.{side}',
        (f'upperleg01.{side}', f'upperleg02.{side}'),
        0.092,
        0.073,
    )
    create_human_legwear(
        side,
        f'lowerleg01.{side}',
        f'foot.{side}',
        (f'lowerleg01.{side}', f'lowerleg02.{side}'),
        0.060,
        0.042,
    )
for costume_part in tuple(body_parts):
    if costume_part.name == 'PleatedSariSkirt' or costume_part.name.startswith(
        ('BharatanatyamFrontFan', 'FanGoldHem', 'FanPleatTrim')
    ):
        world_matrix = costume_part.matrix_world.copy()
        costume_part.parent = avatar_root
        costume_part.parent_type = 'OBJECT'
        costume_part.parent_bone = ''
        costume_part.matrix_parent_inverse = Matrix.Identity(4)
        costume_part.matrix_world = world_matrix

add_character_face_detail(
    'NaturalLipColor',
    (0.0, -0.475, 2.592),
    (0.036, 0.010, 0.010),
    lip_color,
)

flower_white = bpy.data.materials.new(name='JasmineFlower')
flower_white.diffuse_color = (0.96, 0.90, 0.75, 1.0)
hair_shader = hair.node_tree.nodes.get('Principled BSDF')
if hair_shader:
    hair_shader.inputs['Base Color'].default_value = (0.012, 0.006, 0.004, 1.0)
    hair_shader.inputs['Roughness'].default_value = 0.34
add_root_sphere('CombedHairCap', (0.0, 0.035, 1.545), (0.105, 0.078, 0.070), hair, 'head')
add_root_sphere('BraidedHairBun', (0.0, 0.115, 1.525), (0.068, 0.060, 0.060), hair, 'head')
scalp_strands = []
for strand_index in range(20):
    x = -0.073 + strand_index * 0.146 / 19
    scalp_strands.append([
        (x, -0.065, 1.585),
        (x * 1.02, -0.035, 1.565),
        (x * 1.08, 0.012, 1.535),
    ])
add_root_curve('FineCombedHairStrands', scalp_strands, 0.0014, hair)
braid_strands = []
for strand_index in range(3):
    phase_offset = strand_index * 2 * math.pi / 3
    points = []
    for step in range(42):
        progress = step / 41
        points.append((
            -0.080 + 0.055 * progress + 0.012 * math.cos(8 * math.pi * progress + phase_offset),
            -0.105 + 0.008 * math.sin(8 * math.pi * progress + phase_offset),
            1.490 - 0.535 * progress,
        ))
    braid_strands.append(points)
add_root_curve('ThreeStrandTempleBraid', braid_strands, 0.008, hair)
for flower_index in range(10):
    progress = flower_index / 9
    center = (-0.115 + 0.045 * progress, -0.145, 1.485 - 0.47 * progress)
    for petal_index in range(6):
        angle = 2 * math.pi * petal_index / 6
        add_root_sphere(
            'JasmineBraidFlower',
            (
                center[0] + 0.008 * math.cos(angle),
                center[1] - 0.002,
                center[2] + 0.008 * math.sin(angle),
            ),
            (0.006, 0.004, 0.005),
            flower_white,
        )

for sign in (-1, 1):
    add_root_torus(
        'TempleEarringHoop',
        (sign * 0.080, -0.105, 1.425),
        0.022,
        0.004,
        gold,
        (math.pi / 2, 0, 0),
        'head',
    )
    add_root_sphere(
        'TempleEarringRuby',
        (sign * 0.080, -0.110, 1.395),
        (0.010, 0.008, 0.014),
        lip_color,
        'head',
    )
necklace_strands = []
for row, (top, drop) in enumerate(((1.285, 0.045), (1.255, 0.070), (1.225, 0.085))):
    necklace_strands.append([
        (
            0.12 * (-1 + 2 * index / 64),
            -0.142 - 0.018 * (1 - (-1 + 2 * index / 64) ** 2),
            top - drop * (1 - (-1 + 2 * index / 64) ** 2),
        )
        for index in range(65)
    ])
add_root_curve('LayeredTempleNecklaces', necklace_strands, 0.0025, gold)
for bead_index in range(21):
    progress = -1 + 2 * bead_index / 20
    add_root_sphere(
        'TempleNecklaceBead',
        (0.12 * progress, -0.148 - 0.018 * (1 - progress ** 2), 1.285 - 0.045 * (1 - progress ** 2)),
        (0.0045, 0.0045, 0.0045),
        gold,
    )
add_root_sphere('TempleNecklacePendant', (0.0, -0.165, 1.17), (0.018, 0.008, 0.026), gold)
add_root_torus('TempleWaistBelt', (0.0, 0.0, 0.835), 0.17, 0.005, gold)
add_root_sphere('WaistPendant', (0.0, -0.17, 0.82), (0.018, 0.008, 0.028), gold)
for sign in (-1, 1):
    side = 'L' if sign > 0 else 'R'
    for ring_index in range(2):
        add_root_torus(
            'GoldWristBangle',
            (sign * 0.432, -0.16, 0.967 + ring_index * 0.012),
            0.021 + ring_index * 0.001,
            0.003,
            gold,
            (math.pi / 2, 0, 0),
            f'wrist.{side}',
        )
    for ring_index in range(2):
        add_root_torus(
            'GoldGhungrooAnklet',
            (sign * 0.16, -0.032, 0.072 + ring_index * 0.011),
            0.035,
            0.003,
            gold,
            bone_name=f'foot.{side}',
        )
    for bell_index in range(12):
        angle = 2 * math.pi * bell_index / 12
        add_root_sphere(
            'GhungrooBell',
            (
                sign * 0.16 + 0.034 * math.cos(angle),
                -0.032 + 0.034 * math.sin(angle),
                0.083,
            ),
            (0.008, 0.008, 0.008),
            gold,
            f'foot.{side}',
        )
add_root_torus(
    'TempleHeadOrnament',
    (0.0, -0.115, 1.575),
    0.034,
    0.005,
    gold,
    (math.pi / 2, 0, 0),
    'head',
)

scene_mentions_lotus = any(
    'lotus' in (
        ' '.join(scene.get('objects', []))
        + ' '
        + scene.get('source_text', '')
        + ' '
        + str(scene.get('movement_intent', {}).get('target') or '')
    ).lower()
    for scene in manifest['scenes']
)
if scene_mentions_lotus:
    stem_material = bpy.data.materials.new(name='LotusStem')
    stem_material.diffuse_color = (0.08, 0.32, 0.13, 1.0)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=0.035, depth=0.60, location=(0.95, -0.20, -1.55)
    )
    stem = bpy.context.object
    stem.name = 'LotusStem'
    stem.data.materials.append(stem_material)
    bpy.ops.mesh.primitive_uv_sphere_add(location=(0.95, -0.20, -1.18), radius=0.10)
    center = bpy.context.object
    center.name = 'LotusCenter'
    center.scale = (0.18, 0.10, 0.10)
    center.data.materials.append(lotus)
    for index in range(9):
        angle = 2 * math.pi * index / 9
        bpy.ops.mesh.primitive_uv_sphere_add(
            location=(
                0.95 + 0.19 * math.cos(angle),
                -0.20,
                -1.18 + 0.19 * math.sin(angle),
            ),
            radius=0.14,
        )
        petal = bpy.context.object
        petal.name = 'LotusPetal'
        petal.scale = (0.75, 0.30, 1.65)
        petal.rotation_euler[1] = -angle
        petal.data.materials.append(lotus)
        for polygon in petal.data.polygons:
            polygon.use_smooth = True

# A restrained temple stage frames the dancer without changing the camera.
stone = bpy.data.materials.new(name='TempleStone')
stone.use_nodes = True
stone_bsdf = stone.node_tree.nodes.get('Principled BSDF')
stone_bsdf.inputs['Base Color'].default_value = (0.17, 0.055, 0.047, 1)
stone_bsdf.inputs['Roughness'].default_value = 0.82
trim = bpy.data.materials.new(name='TempleTrim')
trim.use_nodes = True
trim_bsdf = trim.node_tree.nodes.get('Principled BSDF')
trim_bsdf.inputs['Base Color'].default_value = (0.48, 0.25, 0.09, 1)
trim_bsdf.inputs['Metallic'].default_value = 0.22
trim_bsdf.inputs['Roughness'].default_value = 0.52
wall_mesh = bpy.data.meshes.new('TempleBackdropMesh')
wall_mesh.from_pydata(
    [(-5.0, 2.0, -2.0), (5.0, 2.0, -2.0), (5.0, 2.0, 5.0), (-5.0, 2.0, 5.0)],
    [],
    [(0, 1, 2, 3)],
)
wall = bpy.data.objects.new('TempleBackdrop', wall_mesh)
bpy.context.collection.objects.link(wall)
wall.data.materials.append(stone)
for x in (-2.65, 2.65):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=0.17, depth=4.4, location=(x, 1.55, 0.12)
    )
    column = bpy.context.object
    column.name = 'TemplePillar'
    column.data.materials.append(trim)
    bpy.ops.object.shade_smooth()
    for z, radius, depth in ((-2.0, 0.34, 0.18), (2.24, 0.31, 0.16)):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=radius, depth=depth, location=(x, 1.55, z)
        )
        capital = bpy.context.object
        capital.name = 'TemplePillarCapital'
        capital.data.materials.append(gold)
        bpy.ops.object.shade_smooth()
arch_curve = bpy.data.curves.new('TempleSanctumArchCurve', 'CURVE')
arch_curve.dimensions = '3D'
arch_curve.resolution_u = 2
arch_curve.bevel_depth = 0.075
arch_curve.bevel_resolution = 3
arch_spline = arch_curve.splines.new('POLY')
arch_steps = 32
arch_spline.points.add(arch_steps - 1)
for index, point in enumerate(arch_spline.points):
    angle = math.pi * index / (arch_steps - 1)
    point.co = (2.65 * math.cos(angle), 1.48, 2.36 + 0.82 * math.sin(angle), 1.0)
arch = bpy.data.objects.new('TempleSanctumArch', arch_curve)
bpy.context.collection.objects.link(arch)
arch.data.materials.append(gold)
for sign in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=16, ring_count=12, radius=0.11, location=(sign * 2.15, 1.10, 1.22)
    )
    lamp_flame = bpy.context.object
    lamp_flame.name = 'TempleLampGlow'
    lamp_flame.data.materials.append(gold)
    bpy.ops.object.light_add(type='POINT', location=(sign * 2.15, 0.95, 1.22))
    lamp_light = bpy.context.object
    lamp_light.name = 'TempleLampLight'
    lamp_light.data.energy = 34
    lamp_light.data.color = (1.0, 0.38, 0.10)
    lamp_light.data.shadow_soft_size = 0.55

# Anklet bells and limbs rest in an outward-kneed araimandi-inspired stance.
floor_material = bpy.data.materials.new(name='TempleStageFloor')
floor_material.use_nodes = True
floor_bsdf = floor_material.node_tree.nodes.get('Principled BSDF')
floor_bsdf.inputs['Base Color'].default_value = (0.055, 0.14, 0.12, 1.0)
floor_bsdf.inputs['Roughness'].default_value = 0.64
floor_bsdf.inputs['Metallic'].default_value = 0.12
bpy.ops.mesh.primitive_plane_add(size=200, location=(0.0, 0.0, -2.0))
floor = bpy.context.object
floor.name = 'GardenFloor'
floor.data.materials.append(floor_material)
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.9, depth=0.04, location=(0.0, 0.0, -1.97))
platform = bpy.context.object
platform.name = 'DancePlatform'
platform.data.materials.append(gold)
bpy.ops.object.modifier_add(type='BEVEL')
bpy.context.object.modifiers[-1].width = 0.035
bpy.context.object.modifiers[-1].segments = 3
bpy.ops.object.shade_smooth()

bpy.context.view_layer.objects.active = arm_obj
arm_obj.select_set(True)
bpy.ops.object.mode_set(mode='POSE')

scene_map = manifest['scenes']

ik_targets = {}
hand_meshes = {}

def add_local_hand_mesh(suffix, sign):
    vertices = []
    faces = []

    def add_extruded_polygon(points):
        first = len(vertices)
        vertices.extend((sign * 1.75 + x, -0.065, 1.10 + z) for x, z in points)
        vertices.extend((sign * 1.75 + x, 0.0, 1.10 + z) for x, z in points)
        size = len(points)
        faces.append(tuple(first + index for index in range(size)))
        faces.append(tuple(first + size + index for index in reversed(range(size))))
        for index in range(size):
            next_index = (index + 1) % size
            faces.append((first + index, first + next_index, first + size + next_index, first + size + index))

    add_extruded_polygon(((-0.07, 0.01), (0.07, 0.01), (0.06, 0.14), (-0.06, 0.14)))
    for finger_index in range(4):
        start_x = (finger_index - 1.5) * 0.031
        end_x = start_x * 1.42
        start_z = 0.115
        end_z = 0.31 - abs(finger_index - 1.5) * 0.025
        half_width = 0.014
        add_extruded_polygon((
            (start_x - half_width, start_z),
            (start_x + half_width, start_z),
            (end_x + half_width * 0.7, end_z),
            (end_x - half_width * 0.7, end_z),
        ))
    thumb_direction = -sign
    add_extruded_polygon((
        (thumb_direction * 0.045, 0.065),
        (thumb_direction * 0.075, 0.045),
        (thumb_direction * 0.14, 0.14),
        (thumb_direction * 0.12, 0.16),
    ))

    mesh = bpy.data.meshes.new('PalmAndMudraFingers_' + suffix)
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(skin)
    hand = bpy.data.objects.new('PalmAndMudraFingers_' + suffix, mesh)
    bpy.context.collection.objects.link(hand)
    hand_group = hand.vertex_groups.new(name='hand_' + suffix)
    hand_group.add(list(range(len(vertices))), 1.0, 'REPLACE')
    hand_armature = hand.modifiers.new('HandArmatureDeformation', 'ARMATURE')
    hand_armature.object = arm_obj
    body_parts.append(hand)
    hand_meshes[suffix] = (hand, [vertex.co.copy() for vertex in hand.data.vertices])

for sign, suffix in ((-1, 'l'), (1, 'r')):
    target = bpy.data.objects.new('HandTarget_' + suffix, None)
    bpy.context.collection.objects.link(target)
    target.location = (sign * 1.95, 0.0, 0.62)
    pole = bpy.data.objects.new('ElbowPole_' + suffix, None)
    bpy.context.collection.objects.link(pole)
    pole.location = (sign * 0.65, -0.70, 2.18)
    constraint = arm_obj.pose.bones['hand_' + suffix].constraints.new('IK')
    constraint.name = 'HandTargetIK'
    constraint.target = target
    constraint.pole_target = pole
    constraint.chain_count = 3
    constraint.pole_angle = math.radians(90)
    constraint.use_stretch = False
    ik_targets[suffix] = target
    if realistic_armature is None:
        add_local_hand_mesh(suffix, sign)

root_motion_base = avatar_root.location.copy()
root_rotation_base = avatar_root.rotation_euler.copy()

def set_pose(bone_name, rotation=(0, 0, 0), location=(0, 0, 0), frame_number=1):
    pose_bone = arm_obj.pose.bones[bone_name]
    pose_bone.rotation_mode = 'XYZ'
    pose_bone.rotation_euler = rotation
    pose_bone.location = location
    pose_bone.keyframe_insert(data_path='rotation_euler', frame=frame_number)
    pose_bone.keyframe_insert(data_path='location', frame=frame_number)


def ease_animation_curves():
    for animated_object in list(bpy.data.objects):
        animation = animated_object.animation_data
        if not animation or not animation.action:
            continue
        for curve in animation.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = 'BEZIER'
                key.handle_left_type = 'AUTO_CLAMPED'
                key.handle_right_type = 'AUTO_CLAMPED'


def get_scene_for_frame(frame_number):
    start = 1
    for scene in scene_map:
        count = int(scene.get('frame_count', 1))
        end = start + count - 1
        if start <= frame_number <= end:
            return scene, start, end
        start = end + 1
    return scene_map[0], 1, 1

for frame in range(1, int(manifest['frame_count']) + 1):
    scene, start_frame, end_frame = get_scene_for_frame(frame)
    text = (scene.get('action', '') + ' ' + scene.get('source_text', '')).lower()
    t = (frame - start_frame) / max(1, end_frame - start_frame)
    phase = t * math.tau * 2.2
    movement_sequence = scene.get('visualization_sequence') or []
    active_movement = ''
    movement_progress = t
    if movement_sequence:
        sequence_position = min(0.999999, max(0.0, t)) * len(movement_sequence)
        movement_index = min(len(movement_sequence) - 1, int(sequence_position))
        movement_progress = sequence_position - movement_index
        active_movement = str(movement_sequence[movement_index]).lower()
    intent = scene.get('movement_intent', {})
    mapped_terms = ' '.join(
        [
            str(intent.get('movement_name') or ''),
            str(intent.get('movement_type') or ''),
            str(intent.get('movement_concept') or ''),
            ' '.join(str(item.get('action') or '') for item in intent.get('actions', [])),
            ' '.join(str(item.get('mudra') or '') for item in scene.get('mudra', [])),
            ' '.join(str(item.get('concept') or '') for item in scene.get('movement_concepts', [])),
        ]
    ).lower()
    bhava_terms = ' '.join(
        [
            str(item.get('expressive_quality') or '')
            + ' '
            + str(item.get('bhava') or '')
            for item in scene.get('bhava', [])
        ]
    ).lower()
    mapped_mudra_terms = ' '.join(
        str(item.get('mudra') or '') for item in scene.get('mudra', [])
        if item.get('status') == 'mapped'
    ).lower()
    choreography = active_movement if movement_sequence else text + ' ' + mapped_terms + ' ' + bhava_terms
    is_anjali = 'anjali' in choreography
    is_prayer = 'pray' in choreography or 'prayer' in choreography or 'worship' in choreography
    is_blessing = 'bless' in choreography
    is_divine = any(
        term in choreography
        for term in ('divine', 'appearance', 'manifested', 'revealed')
    ) or (
        not movement_sequence
        and any(
            term in text
            for term in ('divine', 'appeared', 'appearance', 'filled the temple', 'suddenly')
        )
    )
    is_dancing = 'dance' in choreography
    is_alapadmam = 'alapadmam' in choreography
    expression_text = ' '.join((text, active_movement, mapped_terms, bhava_terms))
    is_joyful = any(term in expression_text for term in ('happy', 'happiness', 'joy', 'gratitude', 'grateful'))
    is_walking = (
        ('enter' in text and not movement_sequence)
        or 'walk' in choreography
        or 'chari' in choreography
        or 'return to center' in choreography
    )
    is_reaching = (
        'reach' in choreography
        or ('hold' in choreography and 'lotus' in text and not movement_sequence)
    )
    is_conch = (
        'conch' in choreography
        or 'shanka' in choreography
        or ('conch' in text and not movement_sequence)
    )
    is_turning = 'turn' in choreography or 'bhramari' in choreography
    if is_anjali or is_prayer:
        hand_goals = {'l': (-0.075, -0.52, 1.92), 'r': (0.075, -0.52, 1.92)}
    elif is_blessing:
        hand_goals = {'l': (-1.20, -0.12, 1.20), 'r': (0.18, -0.48, 1.85)}
    elif is_dancing:
        hand_goals = {'l': (-1.40, -0.22, 1.40), 'r': (1.40, -0.22, 1.40)}
    elif is_reaching or is_alapadmam:
        hand_goals = {'l': (0.82, -0.35, 0.92), 'r': (1.35, -0.20, 1.35)}
    elif is_conch:
        hand_goals = {'l': (-1.30, -0.20, 1.35), 'r': (1.25, -0.32, 1.55)}
    elif is_turning:
        hand_goals = {'l': (-1.38, -0.20, 1.72), 'r': (1.38, -0.20, 1.72)}
    elif is_walking:
        hand_goals = {
            'l': (-1.35, -0.10, 1.25 + 0.15 * math.sin(phase)),
            'r': (1.35, -0.10, 1.25 - 0.15 * math.sin(phase)),
        }
    else:
        hand_goals = {'l': (-1.45, -0.15, 1.35), 'r': (1.45, -0.15, 1.35)}
    transition = max(0.0, min(1.0, (t - 0.06) / 0.60))
    transition = transition * transition * (3 - 2 * transition)
    for suffix, sign in (('l', -1), ('r', 1)):
        start = (sign * 1.95, 0.0, 0.62)
        goal = hand_goals[suffix]
        ik_targets[suffix].location = tuple(
            start[index] + (goal[index] - start[index]) * transition
            for index in range(3)
        )
        ik_targets[suffix].keyframe_insert(data_path='location', frame=frame)

    if realistic_armature is not None:
        hand_is_open = is_anjali or is_prayer or is_alapadmam or is_blessing
        hand_is_closed = any(
            name in mapped_mudra_terms for name in ('mushti', 'kapittha')
        )
        for side in ('L', 'R'):
            for finger_index in range(1, 6):
                if finger_index == 1:
                    curl = 0.20 if hand_is_open else 0.38
                    if hand_is_closed:
                        curl = 0.58
                elif hand_is_closed:
                    curl = 0.62
                elif hand_is_open:
                    curl = 0.045 if is_anjali or is_prayer else 0.0
                else:
                    curl = 0.12 + 0.025 * math.sin(phase + finger_index)
                for segment_index in range(1, 4):
                    finger_bone = realistic_armature.pose.bones.get(
                        f'finger{finger_index}-{segment_index}.{side}'
                    )
                    if finger_bone is None:
                        continue
                    segment_weight = (1.0, 0.72, 0.48)[segment_index - 1]
                    finger_bone.rotation_mode = 'XYZ'
                    finger_bone.rotation_euler = (
                        curl * segment_weight,
                        0.0,
                        (finger_index - 3) * 0.025 * (1 if side == 'L' else -1),
                    )
                    finger_bone.keyframe_insert(
                        data_path='rotation_euler',
                        frame=frame,
                    )

    divine_progress = movement_progress if movement_sequence else t
    divine_envelope = max(0.0, min(1.0, (divine_progress - 0.12) / 0.22))
    divine_envelope = divine_envelope * divine_envelope * (3 - 2 * divine_envelope)
    divine_fade = max(0.0, min(1.0, (0.94 - divine_progress) / 0.22))
    divine_fade = divine_fade * divine_fade * (3 - 2 * divine_fade)
    bloom_light.data.energy = 15 + (760 if is_divine else 0) * divine_envelope * divine_fade
    bloom_light.data.keyframe_insert(data_path='energy', frame=frame)
    global_progress = (frame - 1) / max(1, int(manifest['frame_count']) - 1)
    camera.location.x = 0.10 * math.sin(global_progress * math.tau)
    camera.location.z = 0.72 + 0.035 * math.sin(global_progress * math.pi)
    camera.data.lens = 48 + 1.4 * global_progress
    camera.keyframe_insert(data_path='location', frame=frame)
    camera.data.keyframe_insert(data_path='lens', frame=frame)

    # Keep the Araimandi base alive throughout; scenes layer their specific joints on it.
    root_rotation_offset = (0.0, 0.0, math.radians(4 * math.sin(phase)))
    root_location_offset = (0.0, 0.0, 0.015 * math.sin(phase * 2))
    set_pose('root', root_rotation_offset, root_location_offset, frame)
    set_pose('pelvis', (math.radians(4 * math.sin(phase)), 0.0, math.radians(5 * math.sin(phase)),), (0.0, 0.0, 0.0), frame)
    set_pose('thigh_l', (0.0, math.radians(4 * math.sin(phase)), math.radians(-7)), (0.0, 0.0, 0.0), frame)
    set_pose('thigh_r', (0.0, math.radians(-4 * math.sin(phase)), math.radians(7)), (0.0, 0.0, 0.0), frame)
    set_pose('shin_l', (math.radians(-8 + 4 * math.sin(phase)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
    set_pose('shin_r', (math.radians(-8 - 4 * math.sin(phase)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
    set_pose('foot_l', (math.radians(3 * math.sin(phase)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
    set_pose('foot_r', (math.radians(-3 * math.sin(phase)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)

    if is_walking and not is_anjali and not is_prayer:
        stride = math.sin(phase * 1.7)
        root_rotation_offset = (0.0, 0.0, math.radians(6 * stride))
        root_location_offset = (0.0, 0.65 * t, 0.025 * abs(stride))
        set_pose('root', root_rotation_offset, root_location_offset, frame)
        set_pose('thigh_l', (math.radians(18 * stride), math.radians(4), math.radians(-8)), (0.0, 0.0, 0.0), frame)
        set_pose('shin_l', (math.radians(16 * max(0.0, stride)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('thigh_r', (math.radians(-18 * stride), math.radians(-4), math.radians(8)), (0.0, 0.0, 0.0), frame)
        set_pose('shin_r', (math.radians(16 * max(0.0, -stride)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(-16 * stride), math.radians(8 * stride)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(16 * stride), math.radians(-8 * stride)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(8 * math.sin(phase)), 0.0), (0.0, 0.0, 0.0), frame)
    elif is_anjali or is_prayer:
        raise_phase = max(0.0, min(1.0, (t - 0.08) / 0.55))
        raise_phase = raise_phase * raise_phase * (3 - 2 * raise_phase)
        hold_phase = max(0.0, min(1.0, (t - 0.63) / 0.25))
        upper_y = math.radians(82 * raise_phase)
        upper_z = math.radians(18 + 10 * raise_phase)
        elbow_y = math.radians(-50 * raise_phase)
        set_pose('upper_arm_l', (0.0, upper_y, upper_z), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_l', (0.0, elbow_y, math.radians(10 * raise_phase)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, -upper_y, -upper_z), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_r', (0.0, -elbow_y, -math.radians(10 * raise_phase)), (0.0, 0.0, 0.0), frame)
        set_pose('hand_l', (math.radians(10 * hold_phase), 0.0, math.radians(-8)), (0.0, 0.0, 0.0), frame)
        set_pose('hand_r', (math.radians(-10 * hold_phase), 0.0, math.radians(8)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (math.radians(-5 * hold_phase), math.radians(4 * math.sin(phase)), 0.0), (0.0, 0.0, 0.0), frame)
    elif is_divine:
        reveal = max(0.0, min(1.0, (movement_progress - 0.12) / 0.55))
        reveal = reveal * reveal * (3 - 2 * reveal)
        set_pose('chest', (math.radians(-5 * reveal), 0.0, math.radians(9 * reveal)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(42 * reveal), math.radians(22)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-42 * reveal), math.radians(-22)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (math.radians(-8 * reveal), math.radians(5 * math.sin(phase)), 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('thigh_l', (math.radians(5 * reveal), math.radians(4), math.radians(-8)), (0.0, 0.0, 0.0), frame)
        set_pose('thigh_r', (math.radians(-5 * reveal), math.radians(-4), math.radians(8)), (0.0, 0.0, 0.0), frame)
    elif is_reaching:
        reach_phase = max(0.0, min(1.0, (t - 0.1) / 0.42))
        reach_phase = reach_phase * reach_phase * (3 - 2 * reach_phase)
        set_pose('upper_arm_l', (0.0, math.radians(34 * reach_phase), math.radians(13)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_l', (0.0, math.radians(-28 * reach_phase), 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-12), math.radians(-8)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_r', (0.0, math.radians(-18), 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('chest', (math.radians(4 * reach_phase), 0.0, math.radians(5 * reach_phase)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(18 * reach_phase), math.radians(6)), (0.0, 0.0, 0.0), frame)
    elif is_conch:
        gesture_phase = max(0.0, min(1.0, (t - 0.1) / 0.5))
        set_pose('pelvis', (0.0, 0.0, math.radians(-18 * gesture_phase)), (0.0, 0.0, 0.0), frame)
        set_pose('chest', (0.0, 0.0, math.radians(-12 * gesture_phase)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(9), math.radians(24)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_l', (0.0, math.radians(-16), math.radians(8)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-45 * gesture_phase), math.radians(-35)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_r', (0.0, math.radians(-28), math.radians(-12)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(-16 * gesture_phase), math.radians(-8)), (0.0, 0.0, 0.0), frame)
    elif is_turning:
        turn_angle = math.radians(360 * max(0.0, min(1.0, (t - 0.12) / 0.70)))
        set_pose('pelvis', (0.0, 0.0, turn_angle), (0.0, 0.0, 0.0), frame)
        set_pose('chest', (0.0, 0.0, turn_angle * 0.82), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(32), math.radians(22)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-32), math.radians(-22)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(-20 * math.sin(phase)), 0.0), (0.0, 0.0, 0.0), frame)
    elif is_blessing:
        gesture_phase = max(0.0, min(1.0, (t - 0.08) / 0.45))
        set_pose('upper_arm_l', (0.0, math.radians(8), math.radians(12)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(66 * gesture_phase), math.radians(18)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_r', (0.0, math.radians(-28), math.radians(6)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(-4), 0.0), (0.0, 0.0, 0.0), frame)
    elif is_alapadmam:
        set_pose('upper_arm_l', (0.0, math.radians(30), math.radians(30)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-30), math.radians(-30)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(-5), 0.0), (0.0, 0.0, 0.0), frame)
    elif is_dancing or is_joyful:
        rhythm = math.sin(phase * 2.0)
        alternating_step = math.sin(phase * 2.0)
        root_rotation_offset = (0.0, 0.0, math.radians(8 * rhythm))
        root_location_offset = (0.0, 0.025 * abs(rhythm), 0.035 * abs(rhythm))
        set_pose('root', root_rotation_offset, root_location_offset, frame)
        set_pose('pelvis', (math.radians(5 * rhythm), 0.0, math.radians(9 * rhythm)), (0.0, 0.0, 0.0), frame)
        set_pose('chest', (math.radians(-3 * rhythm), 0.0, math.radians(5 * rhythm)), (0.0, 0.0, 0.0), frame)
        set_pose('thigh_l', (math.radians(17 * alternating_step), math.radians(6), math.radians(-12)), (0.0, 0.0, 0.0), frame)
        set_pose('shin_l', (math.radians(18 * max(0.0, alternating_step)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('thigh_r', (math.radians(-17 * alternating_step), math.radians(-6), math.radians(12)), (0.0, 0.0, 0.0), frame)
        set_pose('shin_r', (math.radians(18 * max(0.0, -alternating_step)), 0.0, 0.0), (0.0, 0.0, 0.0), frame)
        set_pose('foot_l', (math.radians(8 * max(0.0, alternating_step)), 0.0, math.radians(-4)), (0.0, 0.0, 0.0), frame)
        set_pose('foot_r', (math.radians(8 * max(0.0, -alternating_step)), 0.0, math.radians(4)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(26 + 18 * rhythm), math.radians(23 + 12 * math.cos(phase))), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-26 - 18 * rhythm), math.radians(-23 - 12 * math.cos(phase))), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_l', (0.0, math.radians(-18 + 10 * rhythm), math.radians(8)), (0.0, 0.0, 0.0), frame)
        set_pose('forearm_r', (0.0, math.radians(18 - 10 * rhythm), math.radians(-8)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (math.radians(-2 + 5 * math.sin(phase)), math.radians(8 * rhythm), 0.0), (0.0, 0.0, 0.0), frame)
    else:
        set_pose('chest', (0.0, 0.0, math.radians(5 * math.sin(phase))), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_l', (0.0, math.radians(12), math.radians(14)), (0.0, 0.0, 0.0), frame)
        set_pose('upper_arm_r', (0.0, math.radians(-12), math.radians(-14)), (0.0, 0.0, 0.0), frame)
        set_pose('head', (0.0, math.radians(8 * math.sin(phase)), 0.0), (0.0, 0.0, 0.0), frame)

    if realistic_armature is not None:
        avatar_root.location = tuple(
            root_motion_base[index] + root_location_offset[index]
            for index in range(3)
        )
        avatar_root.rotation_euler = tuple(
            root_rotation_base[index] + root_rotation_offset[index]
            for index in range(3)
        )
        avatar_root.keyframe_insert(data_path='location', frame=frame)
        avatar_root.keyframe_insert(data_path='rotation_euler', frame=frame)

    mouth = bpy.data.objects.get('Mouth')
    if mouth:
        if any(term in expression_text for term in ('joy', 'happy', 'happiness', 'grateful', 'gratitude', 'hasya', 'love', 'sringara')):
            mouth.scale = (0.087, 0.025, 0.020)
        elif any(term in bhava_terms for term in ('surprise', 'wonder', 'adbhuta')):
            mouth.scale = (0.047, 0.025, 0.043)
        elif any(term in bhava_terms for term in ('sad', 'sorrow', 'karuna')):
            mouth.scale = (0.067, 0.025, 0.017)
        else:
            mouth.scale = (0.067, 0.025, 0.025)
        mouth.keyframe_insert(data_path='scale', frame=frame)

    for hand, base_vertices in hand_meshes.values():
        for finger_index in range(4):
            first_vertex = 8 + finger_index * 8
            finger_vertices = range(first_vertex, first_vertex + 8)
            center_x = (base_vertices[first_vertex].x + base_vertices[first_vertex + 1].x) / 2
            for vertex_index in finger_vertices:
                vertex = hand.data.vertices[vertex_index]
                base_vertex = base_vertices[vertex_index]
                if 'alapadma' in mapped_mudra_terms:
                    vertex.co.x = center_x + (base_vertex.x - center_x) * 1.8
                    vertex.co.z = base_vertex.z + 0.035
                elif any(name in mapped_mudra_terms for name in ('mushti', 'kapittha')):
                    wrist_height = 1.10
                    finger_base = wrist_height + 0.115
                    vertex.co.z = finger_base + (base_vertex.z - finger_base) * 0.42
                else:
                    vertex.co = base_vertex
        hand.data.update()

ease_animation_curves()
for obj in body_parts:
    obj.select_set(True)

bpy.ops.render.render(animation=True)
""".strip()
        + "\n"
    )
    return script_path


class RiggedBharatanatyamDancerGenerator:
    """Render a real rigged 3D humanoid dancer with Blender in headless mode."""

    name = "HI-Natya Verse Rigged Human Base Dancer"
    version = "2.0"
    repository = "in-project Blender-based 3D dancer renderer"
    license = "CC0 1.0 Universal base mesh; project-created costume, materials, accessories, and animation."

    @classmethod
    def is_available(cls) -> bool:
        return _blender_executable() is not None

    def generate(self, request: StoryDanceGenerationRequest) -> DanceGeneratorOutput:
        if not request.scenes:
            raise ValueError("At least one choreography scene is required.")

        output_dir = request.output_directory
        output_dir.mkdir(parents=True, exist_ok=True)
        blender_path = _blender_executable()
        if blender_path is None:
            raise RuntimeError(
                "Blender is not available in this environment. A real 3D renderer is required for Story-to-Dance."
            )

        frame_dir = output_dir / "blender_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        script_path = _build_blender_animation_script(request, frame_dir)

        env = os.environ.copy()
        env["HI_NATYA_RENDER_MANIFEST"] = str(output_dir / "render_manifest.json")
        env["HI_NATYA_FRAME_DIR"] = str(frame_dir)

        try:
            blender_process = subprocess.run(
                [
                    blender_path,
                    "--background",
                    "--factory-startup",
                    "--python",
                    str(script_path),
                ],
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_log, stderr_log = _save_blender_diagnostics(
                output_dir,
                exc.stdout,
                exc.stderr,
            )
            log_paths = [
                str(path) for path in (stdout_log, stderr_log) if path is not None
            ]
            details = []
            if exc.stdout:
                details.append(f"stdout:\n{_process_output_text(exc.stdout)[-4000:]}")
            if exc.stderr:
                details.append(f"stderr:\n{_process_output_text(exc.stderr)[-4000:]}")
            detail_text = "\n".join(details)
            logs_text = f" Full Blender logs: {', '.join(log_paths)}." if log_paths else ""
            message = f"Blender rendering exceeded the 600-second limit.{logs_text}"
            if detail_text:
                message = f"{message}\n{detail_text}"
            raise RuntimeError(message) from exc
        except subprocess.CalledProcessError as exc:
            stdout_log, stderr_log = _save_blender_diagnostics(
                output_dir,
                exc.stdout,
                exc.stderr,
            )
            log_paths = [
                str(path) for path in (stdout_log, stderr_log) if path is not None
            ]
            details = []
            if exc.stdout:
                details.append(f"stdout:\n{_process_output_text(exc.stdout)[-4000:]}")
            if exc.stderr:
                details.append(f"stderr:\n{_process_output_text(exc.stderr)[-4000:]}")
            detail_text = "\n".join(details)
            logs_text = f" Full Blender logs: {', '.join(log_paths)}." if log_paths else ""
            message = f"Blender failed to render the choreography (exit code {exc.returncode}).{logs_text}"
            if detail_text:
                message = f"{message}\n{detail_text}"
            raise RuntimeError(message) from exc

        expected_frame_count = sum(
            _scene_frame_count(scene, len(request.scenes)) for scene in request.scenes
        )
        rendered_frames = list(frame_dir.glob("frame_*.png"))
        if len(rendered_frames) != expected_frame_count:
            stdout_log, stderr_log = _save_blender_diagnostics(
                output_dir,
                blender_process.stdout,
                blender_process.stderr,
            )
            log_paths = [
                str(path) for path in (stdout_log, stderr_log) if path is not None
            ]
            logs_text = f" Full Blender logs: {', '.join(log_paths)}." if log_paths else ""
            raise RuntimeError(
                f"Blender exited with code {blender_process.returncode} after rendering "
                f"{len(rendered_frames)} frames; expected {expected_frame_count}.{logs_text}"
            )

        mp4_path = output_dir / "dance-performance.mp4"
        ffmpeg = _ffmpeg_executable()
        if ffmpeg is None:
            raise RuntimeError("No FFmpeg encoder was found for the real 3D dance render pipeline.")
        render_pattern = str(frame_dir / "frame_%04d.png")
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-framerate",
                    str(_FPS),
                    "-i",
                    render_pattern,
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    str(_FPS),
                    str(mp4_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("FFmpeg encoding exceeded the 180-second limit.") from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()[-1200:]
            message = "FFmpeg failed to encode the Blender frames."
            if details:
                message = f"{message} {details}"
            raise RuntimeError(message) from exc

        if not mp4_path.exists() or mp4_path.stat().st_size == 0:
            raise RuntimeError("The Blender-based 3D dancer renderer did not produce a valid MP4 output.")

        pose_sequence: list[GeneratorPoseFrame] = []
        scene_results: list[GeneratorSceneResult] = []
        global_frame = 0
        total_frames = sum(_scene_frame_count(scene, len(request.scenes)) for scene in request.scenes)

        for scene_index, scene in enumerate(request.scenes):
            start_frame = global_frame
            scene_frame_count = _scene_frame_count(scene, len(request.scenes))
            movement_sequence = _scene_movement_sequence(scene)
            action_label = " + ".join(
                action.action for action in scene.movement_intent.actions
            ) or scene.action
            direction_label = " → ".join(
                action.direction or "—" for action in scene.movement_intent.actions
            ) or scene.movement_intent.direction
            target = _intent_target(scene)
            expressive_state = _expressive_state(scene)
            mudras = [item.mudra for item in scene.mudra if item.status == "mapped" and item.mudra]
            for local_frame in range(scene_frame_count):
                pose = _pose_for_frame(scene, local_frame, len(request.scenes), set(_target_kinds(scene)))
                pose.update(
                    {
                        "representation": "rigged_3d_humanoid",
                        "scene_id": scene.scene_id,
                        "scene_order": scene.scene_order,
                        "mapping_status": scene.mapping_status,
                        "movement_concepts": [concept.concept for concept in scene.movement_concept],
                        "movement_intent": scene.movement_intent.model_dump(mode="json"),
                        "movement_sequence": movement_sequence,
                        "mudra": mudras,
                        "target": target,
                        "direction": direction_label,
                        "transition": "Blend into the practice pose, then settle into scene-specific 3D choreography.",
                        "expressive_state": expressive_state,
                        "source_provenance": [item.model_dump(mode="json") for item in scene.source_provenance],
                        "candidate_adavu": None,
                        "action": action_label,
                    }
                )
                pose_sequence.append(
                    GeneratorPoseFrame(
                        frame_index=global_frame,
                        timestamp_seconds=global_frame / _FPS,
                        pose_data=pose,
                    )
                )
                global_frame += 1

            scene_results.append(
                GeneratorSceneResult(
                    scene_id=scene.scene_id,
                    scene_order=scene.scene_order,
                    status="generated",
                    generator_label=None,
                    movement_sequence=movement_sequence,
                    mudra=mudras,
                    action=action_label,
                    target=target,
                    direction=direction_label,
                    transition="Blend into the practice pose, then settle into scene-specific 3D choreography.",
                    expressive_state=expressive_state,
                    start_frame_index=start_frame,
                    end_frame_index=global_frame - 1,
                    reason="Generated with a real rigged 3D humanoid dancer and Blender render pipeline.",
                )
            )

        return DanceGeneratorOutput(
            generation_id=request.generation_id,
            story_id=request.story_id,
            dance_plan_id=request.dance_plan_id,
            choreography_id=request.choreography_id,
            fps=_FPS,
            duration_seconds=total_frames / _FPS,
            video_width=_BLENDER_WIDTH,
            video_height=_BLENDER_HEIGHT,
            skeleton_format="rigged_humanoid_3d_armature",
            coordinate_convention="Blender 3D world coordinates; x right, y forward, z up",
            pose_sequence=pose_sequence,
            video_path=mp4_path,
            scenes=scene_results,
            generator_name=self.name,
            generator_version=self.version,
            repository=self.repository,
            license=self.license,
            provenance=[
                "The animated body uses the Innerscene female base mesh, identified as CC0 1.0 Universal in the source GLB metadata.",
                "The project's Blender choreography controls are retargeted to the base mesh's full-body armature; costume, skin shading, hair, and jewelry are rendered 3D geometry.",
                "The result is a stylized 3D animation, not photorealistic video or expert-validated Bharatanatyam choreography.",
                "Asset provenance and licensing are documented in backend/app/assets/README.md.",
            ],
        )


class ProceduralDancerAvatarGenerator:
    """Legacy procedural avatar renderer kept only as an explicit blocker."""

    name = "HI-Natya Verse Legacy Procedural Dancer Avatar"
    version = "deprecated"
    repository = "legacy procedural renderer"
    license = "Not valid for final Story-to-Dance output"

    def generate(self, request: StoryDanceGenerationRequest) -> DanceGeneratorOutput:
        raise RuntimeError(
            "The procedural Story-to-Dance avatar is intentionally disabled. "
            "No fallback to the primitive illustrated character is allowed; configure a licensed rigged 3D dancer asset instead."
        )


def _ffmpeg_executable() -> str | None:
    env_override = os.environ.get("FFMPEG_PATH")
    if env_override:
        candidate = Path(env_override).expanduser()
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    project_root = Path(__file__).resolve().parents[3]
    tool_candidates = [
        project_root / "tools" / "ffmpeg-9.0.1-essentials_build" / "ffmpeg-9.0.1-essentials_build" / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"),
        project_root / "tools" / "ffmpeg" / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"),
        Path("ffmpeg.exe"),
        Path("ffmpeg"),
    ]
    for candidate in tool_candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


class _FFMPEGVideoWriter:
    def __init__(self, video_path: Path, ffmpeg: str) -> None:
        self.video_path = video_path
        self.process = subprocess.Popen(
            [
                ffmpeg,
                "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-pix_fmt", "bgr24",
                "-s", f"{_WIDTH}x{_HEIGHT}",
                "-r", str(_FPS),
                "-i", "-",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-preset", "veryfast",
                "-crf", "23",
                str(video_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def isOpened(self) -> bool:
        return self.process.poll() is None

    def write(self, frame: np.ndarray) -> None:
        if self.process.stdin is None:
            raise RuntimeError("FFmpeg stdin is unavailable.")
        self.process.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        self.process.stdin.flush()

    def release(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.wait(timeout=90)


def _open_h264_writer(video_path: Path) -> cv2.VideoWriter | _FFMPEGVideoWriter:
    if video_path.exists():
        video_path.unlink()

    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    failures: list[str] = []
    for backend, name in (
        (cv2.CAP_MSMF, "Media Foundation"),
        (cv2.CAP_FFMPEG, "FFmpeg"),
    ):
        writer = cv2.VideoWriter(
            str(video_path),
            backend,
            fourcc,
            _FPS,
            (_WIDTH, _HEIGHT),
        )
        if writer.isOpened():
            return writer
        writer.release()
        failures.append(name)
        if video_path.exists():
            video_path.unlink()

    ffmpeg = _ffmpeg_executable()
    if ffmpeg:
        try:
            return _FFMPEGVideoWriter(video_path, ffmpeg)
        except OSError:
            failures.append("FFmpeg CLI")

    raise RuntimeError(
        "No H.264 MP4 encoder is available. Tried: " + ", ".join(failures) + "."
    )


def _validate_browser_video(video_path: Path, expected_frames: int) -> None:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("The H.264 MP4 could not be reopened after encoding.")
    try:
        codec = int(capture.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(
            "ascii",
            errors="replace",
        ).strip("\x00").casefold()
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        first_ok, first_frame = capture.read()
        if frame_count > 0:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
        last_ok, last_frame = capture.read()
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()

    if codec not in {"h264", "avc1"}:
        raise RuntimeError(f"The generated MP4 is not H.264 (detected codec {codec!r}).")
    if frame_count != expected_frames or fps <= 0 or width != _WIDTH or height != _HEIGHT:
        raise RuntimeError("The H.264 MP4 metadata does not match the rendered timeline.")
    if not first_ok or not last_ok or first_frame is None or last_frame is None:
        raise RuntimeError("The H.264 MP4 first or final frame cannot be decoded.")
