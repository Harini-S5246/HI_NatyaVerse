# Narrative evidence contract

This directory is the isolated source of *curated narrative evidence*. It is not connected to Mudra, Bhava, Pose, fusion, inference, or story-generation code. No value in this contract may be derived from a model label, Mudra name/meaning, Bhava label, Pose class, or timestamp alone.

`narrative_evidence.schema.json` is the versioned JSON Schema (currently `1.1.0`). Each record carries record-level provenance and every event carries a non-empty evidence list. Relations, including causal relations, must have their own evidence list: event evidence alone does not establish a relation.

`narrative_evidence.example.json` is deliberately synthetic (`source_type: synthetic_test_fixture`, `production_eligible: false`). It is a test fixture, not a story annotation, and the service rejects it whenever `for_production=True`.

## Performance mode

Every record has independently sourced `performance_mode`. Its only labels are `pure_dance`, `narrative_dance`, and `unknown`. `pure_dance` and `narrative_dance` require `verification_status: verified`; `unknown` requires `verification_status: unknown`. The field has its own source, source reference, and confidence, and must never be derived from ML outputs, Mudra/Bhava/Pose labels, or timestamps.

The eligibility helper blocks a story for `unknown`, and for either known mode when there are no verified narrative events. A `pure_dance` record therefore remains non-narrative by default; independently sourced verified narrative events are required before it could be eligible. This directory contains no real annotation for the discovered Alarippu/Tisra Alarippu video because no explicit supporting source is present in the repository.

## Adding a real expert annotation

1. Obtain a stable source (for example, a named expert annotation or a cited primary-text annotation) with a resolvable `source_reference`.
2. Create a new JSON record using schema version `1.1.0`; do not edit the synthetic fixture or `mudra_knowledge.json`.
3. Supply record-level source fields and a non-empty `evidence` array for every event. Each evidence item must identify its source, source reference, confidence, and notes.
4. Represent unknown information as `{"label": null, "verification_status": "unknown"}`. Do not fill it from model outputs.
5. Add relations only when separately sourced. A causal relation requires its own non-empty causal evidence list.
6. Set `source_type` to an approved real annotation type and `production_eligible` to `true` only after expert review.
7. Validate through `load_narrative_evidence(path, for_production=True)` before any future production integration.

The contract preserves supplied timestamps and source references exactly; it never fills unknown fields or converts an unverified value into a verified claim.
