import type {
  BhavaClassificationResponse,
  MudraClassificationResponse,
  PerformanceInterpretationPackage,
  TechnicalAudioEvidence,
} from '@/types/analysis'

/** Only persisted classification outputs count as model observations. */
export function hasMudraModelObservation(mudra: MudraClassificationResponse): boolean {
  return mudra.prediction_count > 0 || mudra.mudra_events.length > 0 || mudra.frames.length > 0
}

/** Only persisted classification outputs count as model observations. */
export function hasBhavaModelObservation(bhava: BhavaClassificationResponse): boolean {
  return bhava.prediction_count > 0 || bhava.bhava_events.length > 0 || bhava.frames.length > 0
}

/** A technical artifact is available only after the backend has extracted it. */
export function hasTechnicalAudioEvidence(audioEvidence: TechnicalAudioEvidence | null): boolean {
  return audioEvidence?.availability.audio === true
    && audioEvidence.extraction.status === 'extracted'
    && Boolean(audioEvidence.extraction.audio_reference)
    && audioEvidence.production_eligibility.status === 'technical_only'
    && audioEvidence.production_eligibility.narrative_eligible === false
}

/** Narrative availability is determined exclusively by the production package. */
export function hasProductionVerifiedNarrativeEvidence(
  performanceInterpretation: PerformanceInterpretationPackage | null,
): boolean {
  return performanceInterpretation?.production_eligible === true
    && performanceInterpretation.interpretation_status === 'available'
}
