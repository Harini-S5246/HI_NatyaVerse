# Phase 3 – Cultural Knowledge Representation and Retrieval

## Scope and compatibility

Phase 3 adds a versioned knowledge catalogue and source-aware, per-segment cultural retrieval at the existing Fusion boundary. Mudra/Bhava inference, the Phase 1 temporal sequence, Phase 2 temporal alignment, the older `/api/analyze` response, story generation, and frontend behavior are unchanged. Fusion adds an optional `cultural_knowledge_evidence` result field; the existing four-list `evidence` payload remains unchanged for compatibility.

The knowledge loader accepts the original label-keyed JSON format for compatibility with existing fixtures and deployments. The checked-in `mudra_knowledge.json` uses schema version `2.0`; `KnowledgeService` loads `mudra_knowledge.schema.json` from the application package, validates the schema with Draft 2020-12, then validates the document before applying additional semantic checks. Missing or invalid schemas and invalid documents fail closed as `knowledge_unavailable`.

## Record structure

Each entry has a stable `mudra_id`, canonical name, normalized label, explicitly approved aliases, knowledge status, one or more meaning claims, and uncertainty notes. Each claim has:

- a stable claim ID and optional language-independent concept ID;
- localized descriptions;
- context and usage conditions;
- claim-level verification status;
- source references with optional bibliographic fields; and
- uncertainty notes.

Normalization is Unicode NFKC, case-folding, then retaining alphanumeric characters. It is a matching key, not an alias. The catalogue currently contains no approved aliases, so no spelling variants are inferred.

The 11 legacy project-curated glosses are retained verbatim as English namesake descriptions and are marked `partially_verified`, not fully verified. Their source reference retains the legacy string `Abhinaya Darpanam (canonical namesake)`; author, edition, page, and URL remain unspecified. The 37 entries previously marked `pending_research` remain pending with no meaning claims. No contextual meanings, translations, or aliases were added.

## Retrieval algorithm

1. Load and validate the structured document once per service instance; malformed files fail closed and expose a load error.
2. Resolve canonical names and explicitly approved aliases using normalized labels.
3. Return `unknown_label` for no match and `ambiguous_label` for multiple matching entries.
4. Consider only claims whose context conditions are all satisfied. With no context, contextual claims are not selected. Multiple equally applicable claims return `ambiguous_meaning`.
5. Return verified or partially verified claims only when at least one source reference is present. Pending and unverified claims are not returned as cultural meanings; a claim without sources is withheld.

The legacy `ground_mudra` helper preserves its prior fields and adds verification status, claim ID, source references, and uncertainty notes. Legacy `grounded`/`curated` compatibility labels are not verification claims; consumers must retain and display the explicit verification status. Performance interpretation uses the same retrieval service and 0.5 recognition-confidence threshold, withholds meaning for missing, invalid, or low confidence, and carries claim/source/status/uncertainty metadata when meaning is present.

## Recognition and evidence policy

At Mudra evidence assembly and again at Fusion, each Phase 1 temporal segment is resolved independently. The record preserves video/analysis/segment IDs, label, interval, frame indices, supporting evidence IDs, and recognition confidence. A missing, invalid, above-range, or below-0.5 confidence value withholds the meaning claim; frame-level model predictions and confidence values themselves are preserved. The legacy four-list evidence keeps its shape but does not categorize low-confidence Mudra predictions as grounded. This confidence gate is separate from knowledge verification status.

Phase 2 alignment can be copied into an `alignment_observation` field for reference only. It does not choose a meaning, resolve claim ambiguity, or create a Mudra–Bhava semantic relation. Generic FER labels such as Happy and Sad are described as facial-expression observations; they are never translated into classical Bhava or Rasa labels.

Fusion verifies that both modality results belong to the requested video and same effective analysis. Cultural retrieval additionally checks identifiers on the temporal sequence and each segment. Mismatches fail with a conflict error rather than cross-associating evidence.

## API and storage

No public lookup endpoint is added. Fusion stores the additive `cultural_knowledge_evidence` array in its existing result and modality result locations. Existing modality evidence and the legacy `/api/analyze` contract are not changed.

Each evidence item has independent `knowledge_status`, `verification_status`, `recognition_confidence`, optional claim and source references, and a reason when knowledge is unavailable or withheld. Existing `evidence.grounded/detected/unresolved/interpreted` output remains for compatibility and is not the new segment-level authority.

## Limitations

- Current source references are incomplete project-provided descriptions, not fully auditable citations. Accordingly, the 11 namesake claims are partial, not authoritative verification.
- No claim has curated context conditions, alternative interpretations, or localized descriptions beyond the existing English gloss.
- Confidence threshold 0.5 reuses the established Phase 1 low-confidence boundary; it is not a calibrated probability of correct cultural identification.
- Knowledge is cached for the service instance lifetime. Restart the backend after catalogue changes.
- The legacy lookup remains for compatibility; new Phase 3 fusion evidence is the structured, segment-level contract.
