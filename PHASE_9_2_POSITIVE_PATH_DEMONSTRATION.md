# Phase 9.2 — Synthetic Demonstration Fixture

Identifier: `phase-9-2-synthetic-demonstration-001`

This is a test-only, in-memory fixture. It is not an uploaded performance, is not connected to a real analysis ID, and is not genuine evidence for a dancer or performance.

## Demonstrated lifecycle

The focused test module `backend/tests/test_phase_9_2_positive_path_demo.py` exercises explicit synthetic, source-backed evidence through these separate states:

1. Draft: no Performance Interpretation Package, Story unavailable, no provider request.
2. Submitted: no Performance Interpretation Package, Story unavailable, no provider request.
3. Verified but production ineligible: no Performance Interpretation Package, Story unavailable, no provider request.
4. Verified and production eligible: a validated Performance Interpretation Package is persisted to the in-memory store and reaches one provider-neutral `StructuredGenerationRequest`.

The synthetic statement is deliberately generic and bounded to the explicit fixture record:

> Synthetic demonstration record: Event one is explicitly verified.

The deterministic mock provider may return only that statement. A response that adds an unsupported fact is blocked.

## Boundary proof

The in-memory store contains deliberately excluded raw Mudra, Bhava, Fusion, audio, frame, video, and legacy-story sentinel values. The test asserts that none enter the package. The Story integration service is wired to read only `performance_interpretation`; draft, submitted, ineligible, and legacy-story states therefore cannot reach a provider.

The same validated package produces an identical structured request when the deterministic provider is configured as Ollama, Gemini, or OpenAI. The provider selector is constrained so any fallback fails the test.

The test fingerprints all persisted artifacts for real Alarippu analysis `827dcd2e-33b1-4826-8369-3730724e329a` before and after each in-memory fixture run. Any alteration fails the test.

## Run

From `backend` on this checkout:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_phase_9_2_positive_path_demo.py -q
```
