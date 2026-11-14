# Phase 8F — Final System Validation and Research Results Consolidation

Date: 2026-09-10

This report records repository state and validation results. It does not add or alter models, datasets, inference, narrative evidence, or the real Alarippu analysis.

## 1. Component status

| Component | Actual implementation and production role | Status / evidence classification | Known limitations |
| --- | --- | --- | --- |
| Video upload | `upload_service.save_upload` validates configured extensions and size, writes a UUID-named upload, then validates video metadata. The frontend upload page calls `/api/upload`. | Connected to the frontend workflow; source artifact. | Upload is local filesystem storage; maximum size defaults to 500 MB. |
| Frame extraction | `frame_service.extract_sampled_frames` uses OpenCV to persist JPEGs and a manifest. The frontend requests it at a 1-second interval before classification. | Connected; processing evidence. | Sampling is interval-based and not an interpretation of motion. |
| Mudra classification | `mudra_service.classify_video_frames` loads manifest frames, runs the configured Keras model, groups label runs, applies persisted knowledge lookup, and saves `mudra`. | Connected; model observations plus separate curated references/unresolved observations. | Labels/confidences are classifier output; no reproducible held-out accuracy artifact was found. |
| Bhava classification | `bhava_service.classify_video_bhava` loads the same manifest frames, runs the configured Keras model, groups label runs, and saves `bhava`. | Connected; model observations. | FER2013 foundation labels are not verified performer emotion or narrative intent. |
| Pose component | `PoseModel` loads a BiLSTM artifact for 20x132 landmark sequences. `frame_analysis` can read an optional `pose` result. The standard frontend upload workflow does not create a pose modality artifact. | Model artifact exists; unavailable in the current production evidence pipeline. | No live landmark-extraction/persisted-pose stage is connected to the frontend workflow. |
| Fusion | `fusion_service.fuse_video` reads saved Mudra and Bhava modalities, aligns time intervals, and saves `fusion`. | Connected; processing evidence. | It explicitly does not infer semantic relations or narrative meaning. |
| Technical audio evidence | `audio_evidence_service` probes/extracts an audio stream and persists `audio_evidence` with `technical_only` and `narrative_eligible: false`. | Endpoint/artifact implemented; technical evidence only. The standard frontend upload workflow does not request this endpoint automatically. | FFmpeg/ffprobe are required. Audio is not lyrics, meaning, or story evidence. |
| Curated knowledge grounding | `knowledge_service` maps recognized Mudra labels to entries in `mudra_knowledge.json`; persisted Fusion evidence retains grounded and unresolved items. | Connected as curated reference information. | A mapping does not establish dancer intent or performance meaning. |
| Narrative evidence workflow | `/narrative-evidence` accepts explicit source-backed records or submissions and validates provenance. | Separate, explicit workflow; human-supplied evidence. | It never derives narrative evidence from model/fusion/audio artifacts. |
| Narrative review lifecycle | `narrative_evidence_review_service` permits draft/submitted records, then explicit verified/rejected review and eligibility marking. | Implemented; human-verification metadata. | New submissions cannot self-verify; no evidence was created for Alarippu. |
| Performance Interpretation Package | A package is built only from validated production-eligible narrative evidence and persisted as `performance_interpretation`. | Implemented; sole production Story input. | No package exists for the real Alarippu analysis. |
| Story generation | Live `/videos/{id}/story` uses `story_integration_service`, which reads only the matching package and invokes `narrative_generation_service`. | Package-only validated boundary. Missing package returns `unavailable` with no narrative. | Legacy `story_service.py` remains in the repository but is not the live Story route boundary. The frontend upload page still calls the Story endpoint and treats any response as stage completion; unavailable remains a valid response. |
| LLM provider abstraction | `app.services.llm` exposes Ollama, Gemini, and OpenAI providers; `narrative_generation_service` chooses the configured provider and validates structured output. | Implemented behind the package-only generation boundary. | Provider failure/empty output is blocked; tests assert no fallback. Credentials/local service are environment-dependent. |
| Frontend Analysis evidence/provenance UI | `getCanonicalAnalysis` reads Mudra, Bhava, Fusion, audio evidence, package, and review artifacts. Evidence status, expandable provenance, and the timeline render from those fields. | Connected; explainability UI. | It deliberately does not read legacy story artifacts to determine evidence availability and does not invoke Story/LLM generation. |

## 2. Model results consolidation

Only values found in committed model metadata or persisted validation artifacts are reported.

| Model | Deployment classification / architecture | Classes and dataset | Evaluation results available | Limitations |
| --- | --- | --- | --- | --- |
| Mudra | Deployed image classifier: `Natya_Mudra_EfficientNetB0_FineTuned.keras`; adapter identifies it as EfficientNetB0. | 49 labels in `mudra_class_names.json`. Dataset and evaluation split are not documented in reproducible artifacts. | No test accuracy, precision, recall, or F1 artifact found. `validation_mudra_predictions.json` contains synthetic-input predictions only, not a held-out evaluation. | Model-quality diagnostic artifacts exist, but are not a reproducible accuracy evaluation. |
| Bhava | Deployed foundation image classifier: `bhava_phase3_moderated_best.keras`; metadata says EfficientNetB0. | 7 classes: Angry, Disgust, Fear, Happy, Sad, Surprise, Neutral. Metadata identifies FER2013. Evaluation split name/count is not documented. | Metadata and persisted validation report: test accuracy 0.5783, macro F1 0.5372, weighted F1 0.5670. Precision/recall are not available. | Metadata describes a foundation model with a next stage of Bharatanatyam-specific multimodal adaptation; it is not evidence of internal emotion or intent. |
| Pose | Experimental/diagnostic-only relative to the live frontend pipeline: `Natya_Pose_BiLSTM_Best.keras`; adapter expects 20x132 landmark sequences. | 8 labels in `pose_class_names.json`: Competition, Devi, Krishna, Padam, Shiva, Solo, Varnam, story based video. Dataset and split are not documented. | No test accuracy, precision, recall, or F1 artifact found. | No production landmark extraction and persisted pose-analysis stage is connected to the standard upload workflow. |

## 3. Real Alarippu validation

Analysis ID: `827dcd2e-33b1-4826-8369-3730724e329a`

Read-only artifact check:

| Item | Result |
| --- | --- |
| Mudra artifact | Present; 191 persisted predictions. |
| Bhava artifact | Present; 191 persisted predictions. |
| Fusion artifact | Present. |
| Technical audio artifact | Present; `availability.audio: true`, extraction status `extracted`, production status `technical_only`. |
| Pose artifact | Absent. |
| Curated knowledge references | 6 persisted grounded references. |
| Unresolved observations | 17 persisted unresolved observations. |
| Narrative evidence review | Absent. |
| Performance Interpretation Package | Absent. |
| Live Story integration result | `unavailable`; no narrative returned: “No production-verified narrative evidence is currently available for this performance. The system does not generate unsupported story content.” |

The legacy persisted story artifact was not used for this validation and is not used by the Analysis evidence loader.

## 4. Positive-path safety validation

The maintained synthetic/in-memory tests in `tests/test_verified_story_end_to_end.py` confirm:

- Draft and submitted evidence cannot reach a provider.
- Rejected and verified-but-ineligible evidence cannot produce a package or reach a provider.
- Verified, production-eligible synthetic evidence compiles into a Performance Interpretation Package and reaches exactly one configured provider-neutral boundary.
- Synthetic raw Mudra, Bhava, Fusion, and audio values are deliberately placed in the in-memory store and asserted absent from the provider prompt.
- Unsupported generated additions are blocked.

`tests/test_story_integration_service.py` further verifies that a missing package, including the Alarippu case, returns `unavailable`, and that only the matching package is passed unchanged to Phase 6.

Focused run: these two modules passed 18 tests in 0.36 seconds.

Therefore Mudra alone, Bhava alone, Fusion alone, audio, curated knowledge, and legacy story artifacts are not verified evidence inputs to the live Story integration route.

## 5. Reproducibility requirements

- Python dependencies: install `backend/requirements.txt` in a Python environment compatible with TensorFlow 2.16 or later as declared there. No Python version is pinned by the repository.
- Node dependencies: run `npm install` in `frontend`; `package.json` does not pin a Node/npm engine version.
- Model artifacts: the configured defaults require the three `.keras` files and class/metadata JSON files under `backend/models/`.
- FFmpeg: technical audio extraction requires both `ffmpeg` and `ffprobe`, resolved from `FFMPEG_PATH` / `FFPROBE_PATH`, system `PATH`, or project-local `tools/**/bin`.
- Backend startup: from `backend`, run `python -m uvicorn app.main:app --reload` after installing dependencies and configuring environment values.
- Frontend startup: from `frontend`, run `npm run dev`.
- Backend tests: from `backend`, run `..\\.venv\\Scripts\\python.exe -m pytest tests -q` on this Windows checkout, or use the active environment's `python -m pytest tests -q`.
- Frontend production build: from `frontend`, run `npm.cmd run build` on this Windows checkout, or `npm run build` where shell policy permits it.
- Environment: copy `backend/.env.example` to `backend/.env` when provider credentials or overrides are needed. Do not commit credentials. `VITE_API_BASE_URL` may be set in the frontend environment. Paths, upload limits, host/port/CORS, model paths, FFmpeg paths, and provider selection are documented in `backend/.env.example`.

## 6. Validation results and known limitations

- Maintained backend suite: `188 passed in 3.00s` (`pytest tests -q`).
- Frontend production build: `npm.cmd run build` passed; Vite built in 2.65 seconds with no TypeScript errors.
- No separate frontend unit-test framework is configured in `frontend/package.json`.
- Root-level diagnostic scripts and legacy services are outside the maintained `backend/tests` suite; they were not treated as regressions.
- The frontend upload flow invokes the Story endpoint, but the endpoint safely returns an unavailable response without a package. The Analysis page itself does not invoke it.

## 7. Change declaration

No ML model, dataset, model inference semantics, Fusion semantics, audio semantics, LLM/provider behavior, narrative evidence, Performance Interpretation Package, or real Alarippu artifact was modified during this Phase 8F audit.
