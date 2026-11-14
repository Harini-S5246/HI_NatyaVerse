# Story-to-Dance performance generation

## Current capability

The one-click `POST /api/story-to-dance/stories/workflow` endpoint creates the
story record, asks the configured text provider for a source-grounded scene
plan, builds a deterministic visualization sequence, and invokes the local
renderer. It returns success only after the video has been validated. A
client-supplied UUID makes duplicate workflow submissions replay the saved
result; `GET /api/story-to-dance/stories/workflow/{request_id}` retrieves it
later. Story and generation records are JSON files under `RESULTS_DIR`; the
synchronous renderer does not use a database or background-job queue.

`RiggedBharatanatyamDancerGenerator` imports the bundled Innerscene CC0 female
base mesh and its 163-bone armature, retargets the existing Story-to-Dance
control rig, and creates the costume and accessories as Blender geometry. The
renderer outputs 720×810 frames at 20 FPS, and FFmpeg encodes an H.264 MP4.
Scene durations are 4 seconds by default (3.5 seconds for
four-scene stories), 5 seconds for one scene, and the existing 5/7-scene
timing profiles.
The service validates codec, dimensions, duration, frame count, and first/last
frame decoding before publishing the video. Files are stored at
`RESULTS_DIR/story_to_dance/generations/{story_id}/{generation_id}/`.

The planner maps only concepts present in the curated movement vocabulary and
Mudra knowledge. Chari travel and Bhramari turning remain review-required
concepts; curated Anjali, Shanka, and Alapadmam names are labeled as
namesakes. Prayer, blessing, dance, and source-expression cues are explicitly
creative visualizations. The Blender renderer uses the ordered
`visualization_sequence` and scene duration; the response separately reports
rendered scenes and source-supported concepts. No Adavu or expert-validated
movement label is assigned.

The UI presents the output as **AI-assisted Story-to-Bharatanatyam 3D
Animation**. It is a procedural, project-built 3D visualization—not
photorealistic AI video, a captured dancer, or expert-validated choreography.
The human base mesh has no image textures; its skin is shaded procedurally.
Its rig includes articulated hands and feet, while story-specific pose
retargeting remains a creative visualization rather than a canonical dance
performance. Asset source and CC0 licensing are recorded in
`backend/app/assets/README.md`.
No reference image, driving video, manual trimming, ComfyUI workflow, or
external video-generation API is required. The bundled
`Natya_Pose_BiLSTM_Best.keras` classifier is not used by the renderer.

## Candidates reviewed, not integrated

**MDM** is the closest research candidate. Its code is MIT-licensed and its
official README links HumanML3D checkpoints. The documented environment is
Python 3.7.13, PyTorch 1.7.1, CUDA 11.0, and a CUDA-capable GPU. Its
HumanML3D output is 22-joint XYZ motion at 20 FPS, with a documented maximum
duration of 9.8 seconds; the standard renderer produces a stick-figure MP4.
SMPL mesh rendering requires additional separately licensed assets and a
GPU-based fitting step. The checkpoint links do not state a separate weights
license, and HumanML3D does not establish Bharatanatyam, Chari, or Bhramari
coverage.

**MotionGPT** documents 22-joint motion arrays and a Blender-based MP4
rendering path. Its source code is MIT-licensed, but its public model card
only specifies the generic label `cc`, not the exact checkpoint license. The
repository also warns that an unseen instruction can be understood without
the corresponding motion being generated reliably.

**MotionDiffuse** has downloadable HumanML3D weights and a documented CPU
visualization path, but its official license restricts use to non-commercial
purposes, so it is not a suitable general integration candidate.

None of these research model candidates is integrated. No candidate model,
checkpoint, or dataset was downloaded or executed; the in-project Blender
renderer described above is separate from these candidates.

Authoritative references:

- [MDM README](https://github.com/GuyTevet/motion-diffusion-model/blob/main/README.md),
  [code license](https://github.com/GuyTevet/motion-diffusion-model/blob/main/LICENSE),
  [HumanML3D data terms](https://github.com/EricGuo5513/HumanML3D/blob/main/README.md)
- [MotionGPT README](https://github.com/OpenMotionLab/MotionGPT),
  [model card](https://huggingface.co/OpenMotionLab/MotionGPT-base)
- [MotionDiffuse license](https://github.com/MotrixLab/MotionDiffuse/blob/main/LICENSE)

## Generator contract

`RiggedBharatanatyamDancerGenerator.generate(request)` in
`app/services/story_dance_avatar_service.py` implements the `DanceGenerator`
contract consumed by `app/services/dance_generation_service.py`. A request
binds the ordered choreography to `story_id`, `dance_plan_id`,
`choreography_id`, and a new `generation_id`; its output directory is unique
to that request. It includes source-grounded scene text, actions,
Mudra/Bhava records, curated movement concepts, the ordered visualization
sequence, and estimated duration.

The generator returns:

- contiguous, temporally ordered pose frames;
- actual measured FPS and duration;
- actual validated video width and height;
- generation/story/plan/choreography IDs matching the current request;
- the generator's documented skeleton format and coordinate convention;
- a temporally ordered pose sequence and per-scene frame and time ranges;
- a non-empty, decodable MP4 in the newly-created request output directory,
  whose FPS, duration, and frame count match the returned metadata;
- per-scene statuses that exactly preserve scene IDs and order; a rendered
  scene is distinct from a source-supported movement mapping;
- generator name/version, source repository, license, and provenance.

The Blender script is stored as `blender_rigged_dancer.blender-script` rather
than a `.py` file. This prevents development servers such as Uvicorn
`--reload` from treating generated render inputs under `RESULTS_DIR` as source
changes and restarting the backend while Blender is running. If Blender exits
unsuccessfully or does not render the expected frame count, complete captured
stdout and stderr are saved as `blender.stdout.log` and `blender.stderr.log`
in that generation directory; the failure result includes the exit code and
diagnostic excerpts. The known
`TBBmalloc: skip allocation functions replacement in ucrtbase.dll` warning
can appear on a successful Blender startup and is not by itself treated as a
render failure.

Before a result can be marked completed, the service validates those values,
checks scene/frame mapping metadata, MP4 readability, FPS, duration, and frame
count, then stores it under the current story/generation IDs while verifying
all four identities in metadata and routes. Scene timing is derived from
validated frame ranges and actual FPS. A missing renderer or invalid result
produces an explicit unavailable/failed result with no video URL.

## Still required for authentic or learned choreography

The procedural renderer does not supply a learned or canonical choreography
model. Authentic/expert-validated performance claims still require an
approved model artifact and weights license; verified checkpoint, dataset,
body-model, and dependency terms; runtime compatibility; a validated dancer
renderer; and mappings reviewed by qualified Bharatanatyam experts. The
existing classifier and generic text-prompting models cannot establish those
capabilities.
