/**
 * Domain types for HI-Natya Verse.
 *
 * These interfaces describe the shape of data returned by the Python AI
 * backend. Because the exact backend response shape may evolve, most
 * fields are marked optional — components must treat a missing field as
 * "not provided" rather than assuming a default or fabricating a value.
 */

export type EvidenceLevel = 'high' | 'moderate' | 'low' | 'unknown'

export type GroundingStatus = 'grounded' | 'unresolved' | 'detected' | 'interpreted'
export type KnowledgeVerificationStatus = 'verified' | 'partially_verified' | 'pending_research' | 'unverified' | string

export type AnalysisStatusValue =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'unknown'

/** Supported interface / story languages. Value is the language name the backend expects. */
export type SupportedLanguage =
  | 'English'
  | 'Tamil'
  | 'Hindi'
  | 'Malayalam'
  | 'Telugu'
  | 'Kannada'
  | 'Bengali'

export interface LanguageOption {
  value: SupportedLanguage
  label: string
  nativeLabel: string
}

/* ------------------------------------------------------------------ */
/* Confidence / evidence primitives                                    */
/* ------------------------------------------------------------------ */

export interface ConfidenceValue {
  /** 0–1 or 0–100 depending on backend; components normalize via utils/format. */
  score?: number
  level?: EvidenceLevel | string
}

export interface EvidenceStrength {
  overall_evidence_strength?: number
  evidence_strength?: number
  evidence_level?: EvidenceLevel | string
  validation_score?: number
  validation_level?: EvidenceLevel | string
}

/* ------------------------------------------------------------------ */
/* Mudra                                                               */
/* ------------------------------------------------------------------ */

export interface MudraDetection {
  name: string
  meaning?: string | null
  confidence?: number
  grounded: boolean
  status?: GroundingStatus
  knowledge_status?: KnowledgeVerificationStatus | null
  verification_status?: KnowledgeVerificationStatus | null
  claim_id?: string | null
  source_references?: string[]
  uncertainty_notes?: string[]
  uncertainty_reason?: string | null
  occurrence_count?: number
  timestamps?: number[]
  segment_start?: number
  segment_end?: number
  notes?: string
}

export interface MudraAnalysis {
  primary?: MudraDetection
  detections: MudraDetection[]
  mudra_confidence?: number
}

/* ------------------------------------------------------------------ */
/* Bhava (emotional expression)                                        */
/* ------------------------------------------------------------------ */

export interface BhavaSegment {
  label: string
  start?: number
  end?: number
  confidence?: number
}

export interface BhavaAnalysis {
  dominant_emotion?: string
  confidence?: number
  bhava_confidence?: number
  evidence_level?: EvidenceLevel | string
  segments?: BhavaSegment[]
}

/* ------------------------------------------------------------------ */
/* Pose                                                                 */
/* ------------------------------------------------------------------ */

export interface PoseSegment {
  label: string
  start?: number
  end?: number
  confidence?: number
}

export interface PoseAnalysis {
  primary_pose?: string
  confidence?: number
  pose_confidence?: number
  segments?: PoseSegment[]
}

/* ------------------------------------------------------------------ */
/* Audio / lyrics                                                       */
/* ------------------------------------------------------------------ */

export interface AudioAnalysis {
  audio_status?: string
  audio_type?: 'rhythmic-only' | 'lyrical' | string
  lyrics_available?: boolean
  lyrics?: string | null
  transcription?: string | null
  audio_confidence?: number
}

/* ------------------------------------------------------------------ */
/* Evidence panel                                                       */
/* ------------------------------------------------------------------ */

export interface EvidenceItem {
  id: string
  label: string
  category: GroundingStatus
  detail?: string
  confidence?: number
  knowledge_status?: KnowledgeVerificationStatus | null
  verification_status?: KnowledgeVerificationStatus | null
  claim_id?: string | null
  source_references?: string[]
  uncertainty_notes?: string[]
  uncertainty_reason?: string | null
}

export interface Evidence {
  grounded: EvidenceItem[]
  detected: EvidenceItem[]
  unresolved: EvidenceItem[]
  interpreted: EvidenceItem[]
}

/* ------------------------------------------------------------------ */
/* Full analysis result                                                 */
/* ------------------------------------------------------------------ */

export interface PerformanceMeta {
  performance_name?: string
  performance_type?: string
  duration_seconds?: number
  uploaded_at?: string
}

export interface AnalysisStatus {
  analysis_id: string
  status: AnalysisStatusValue
  message?: string
  stage?: string
  progress?: number
}

export interface AnalysisResult {
  analysis_id: string
  performance?: PerformanceMeta
  mudra?: MudraAnalysis
  bhava?: BhavaAnalysis
  pose?: PoseAnalysis
  audio?: AudioAnalysis
  evidence?: Evidence
  overall_evidence_strength?: number
  evidence_level?: EvidenceLevel | string
  confidence?: ConfidenceValue
}

/** The single source of truth for a completed video analysis. */
export interface CanonicalAnalysis {
  videoId: string
  mudra: MudraClassificationResponse
  bhava: BhavaClassificationResponse
  fusion: FusionResult
  audioEvidence: TechnicalAudioEvidence | null
  performanceInterpretation: PerformanceInterpretationPackage | null
  narrativeEvidenceReview: NarrativeEvidenceReviewSummary | null
}

/** Persisted technical artifact. It is never narrative evidence. */
export interface TechnicalAudioEvidence {
  analysis_id: string
  video_id: string
  source: { type: 'uploaded_video'; reference: string; version: string }
  availability: { audio: boolean | null; reason: string | null }
  technical_properties: {
    duration: number | null
    timeline_start_time: number | null
    sample_rate: number | null
    channels: number | null
    codec: string | null
    container: string | null
  }
  extraction: { status: 'pending' | 'extracted' | 'no_audio' | 'unavailable' | 'failed'; audio_reference: string | null }
  production_eligibility: { status: 'technical_only'; narrative_eligible: false }
}

/** Persisted package that is the sole eligible input to live Story generation. */
export interface PerformanceInterpretationPackage {
  analysis_id: string
  video_id: string
  production_eligible: boolean
  interpretation_status: 'available' | 'unavailable'
  events: Array<{ event_id: string; type: string }>
}

/** Explicit human-review metadata; an empty record list means no submissions. */
export interface NarrativeEvidenceReviewSummary {
  analysis_id: string
  video_id: string
  records: Array<{ status: 'draft' | 'submitted' | 'verified' | 'rejected'; production_eligibility: { status: 'eligible' | 'ineligible' } }>
  story_eligible: boolean
  story_eligibility_reason: string
}

/* ------------------------------------------------------------------ */
/* Story / interpretation                                               */
/* ------------------------------------------------------------------ */

export interface StoryInterpretationItem {
  id: string
  statement: string
  supporting_evidence: string[]
  confidence?: number | null
  status: string
  knowledge_status?: KnowledgeVerificationStatus | null
  verification_status?: KnowledgeVerificationStatus | null
  claim_id?: string | null
  source_references?: string[] | null
  uncertainty_notes?: string[] | null
}

/**
 * Evidence-grounded story response from POST /api/videos/{video_id}/story.
 * Follows the deterministic template-based generation with curated meanings.
 */
export interface StoryResponse {
  analysis_id: string
  status: 'completed' | 'insufficient_grounded_evidence' | 'generation_failed'
  language: string
  title: string | null
  story: string | null
  interpretations: StoryInterpretationItem[]
  supporting_evidence: string[]
  unresolved_evidence: string[]
  message: string | null
  provider?: string | null
  model?: string | null
  generation_method?: string | null
  narrative_confidence?: string | null
  evidence_coverage?: Record<string, number | boolean> | null
}

/** Validated Phase 6 generation contract returned by the Story endpoint. */
export interface NarrativeGenerationResponse {
  schema_version: '1.0.0'
  analysis_id: string
  video_id: string
  mode: 'pure_dance' | 'narrative_dance' | 'evidence_based' | 'unknown'
  status: 'generated' | 'unavailable' | 'blocked' | 'retryable'
  language: string
  presentation_version?: string | null
  title: string | null
  narrative: string | null
  evidence_coverage: number
  used_event_ids: string[]
  limitations: string[]
  provider: 'gemini' | 'ollama' | 'openai'
  model: string
  message: string | null
  retry_after_seconds?: number | null
  error_code?: string | null
  package_eligible?: boolean
  package_fingerprint?: string | null
  package_evidence_coverage?: number
}

/**
 * Legacy story type; kept for backward compatibility.
 * Prefer StoryResponse for new code.
 */
export interface StoryInterpretation {
  analysis_id: string
  language: SupportedLanguage | string
  title?: string
  summary?: string
  narrative?: string
  emotional_interpretation?: string
  grounded_gesture_interpretation?: string
  evidence_based_observations?: string[]
  uncertainties?: string[]
  limitations?: string
}

export interface MultilingualStory {
  analysis_id: string
  available_languages: (SupportedLanguage | string)[]
  stories?: Partial<Record<SupportedLanguage, StoryInterpretation>>
}

/* ------------------------------------------------------------------ */
/* Fusion result (mudra + bhava timeline + evidence)                   */
/* ------------------------------------------------------------------ */

export interface FusionTimelineRow {
  start_time: number
  end_time: number
  mudra?: string
  mudra_confidence?: number
  mudra_grounded?: boolean
  mudra_knowledge_status?: KnowledgeVerificationStatus | null
  mudra_verification_status?: KnowledgeVerificationStatus | null
  mudra_claim_id?: string | null
  mudra_source_references?: string[]
  mudra_uncertainty_notes?: string[]
  bhava?: string
  bhava_confidence?: number
  [key: string]: unknown
}

export interface FusionSummary {
  dominant_mudra?: string | null
  dominant_bhava?: string | null
  mudra_event_count: number
  bhava_event_count: number
  average_mudra_confidence?: number | null
  average_bhava_confidence?: number | null
  frame_count: number
}

export interface FusionResult {
  analysis_id: string
  status: string
  timeline: FusionTimelineRow[]
  summary: FusionSummary
  evidence: Evidence
}

/* ------------------------------------------------------------------ */
/* Mudra classification response                                        */
/* ------------------------------------------------------------------ */

export interface MudraFrame {
  frame_number: number
  timestamp: number
  filename: string
  mudra: string
  confidence: number
  grounded: boolean
  status: GroundingStatus
  meaning?: string | null
  knowledge_status?: KnowledgeVerificationStatus | null
  verification_status?: KnowledgeVerificationStatus | null
  claim_id?: string | null
  source_references?: string[]
  uncertainty_notes?: string[]
  uncertainty_reason?: string | null
}

export interface MudraEvent {
  mudra: string
  start_time: number
  end_time: number
  confidence: number
  frame_count: number
}

export interface MudraClassificationResponse {
  analysis_id: string
  frame_count: number
  prediction_count: number
  mudra_events: MudraEvent[]
  summary: {
    dominant_mudra?: string | null
    average_confidence?: number | null
  }
  grounded_count: number
  frames: MudraFrame[]
  evidence: Evidence
  mudra?: {
    detections: MudraDetection[]
  }
}

/* ------------------------------------------------------------------ */
/* Bhava classification response                                        */
/* ------------------------------------------------------------------ */

export interface BhavaFrame {
  frame_number: number
  timestamp: number
  filename: string
  bhava: string
  confidence: number
}

export interface BhavaEvent {
  bhava: string
  start_time: number
  end_time: number
  confidence: number
  frame_count: number
}

export interface BhavaClassificationResponse {
  analysis_id: string
  video_id: string
  status: string
  frame_count: number
  prediction_count: number
  bhava_events: BhavaEvent[]
  summary: {
    dominant_bhava?: string | null
    average_confidence?: number | null
  }
  frames: BhavaFrame[]
  evidence: Evidence
  bhava?: {
    dominant_emotion?: string
    confidence?: number
    detections: Array<{ name: string; confidence: number }>
    segments: BhavaSegment[]
  }
}

/* ------------------------------------------------------------------ */
/* Frame-level analysis                                                */
/* ------------------------------------------------------------------ */

/** Prediction for a single modality at a frame */
export interface FramePrediction {
  label: string | null
  confidence: number | null
  status: 'detected' | 'unresolved' | 'unavailable'
  meaning?: string | null
  explanation?: string | null
  knowledge_status?: KnowledgeVerificationStatus | null
  verification_status?: KnowledgeVerificationStatus | null
  claim_id?: string | null
  source_references?: string[]
  uncertainty_notes?: string[]
  uncertainty_reason?: string | null
}

/** Frame-level prediction combining all modalities */
export interface FrameLevelAnalysis {
  frame_number: number
  timestamp: number
  filename: string
  frame_url?: string
  mudra: FramePrediction
  bhava: FramePrediction
  pose: FramePrediction
}

export interface FrameAnalysisEvent {
  modality: 'mudra' | 'bhava' | 'pose'
  label: string | null
  start_timestamp: number
  end_timestamp: number
  first_frame_number: number
  last_frame_number: number
  representative_frame: FrameLevelAnalysis
  frame_count: number
  average_confidence: number | null
}

/** Complete frame-level analysis response */
export interface FrameLevelAnalysisResponse {
  video_id: string
  status: 'completed' | 'partial' | 'unavailable'
  total_frames: number
  frames: FrameLevelAnalysis[]
  events?: {
    mudra: FrameAnalysisEvent[]
    bhava: FrameAnalysisEvent[]
    pose: FrameAnalysisEvent[]
  }
  event_persistence_frames?: number
  occurrences?: {
    mudra: Record<string, number>
    bhava: Record<string, number>
  }
  warnings?: {
    mudra?: ModelRepetitionWarning | null
    bhava?: ModelRepetitionWarning | null
  }
}

export interface ModelRepetitionWarning {
  type: 'repetitive_predictions'
  message: string
  dominant_label: string
  dominant_frames: number
  total_frames: number
}

/** Summary statistics for frame-level analysis */
export interface FrameAnalysisSummary {
  video_id: string
  total_frames: number
  mudra: {
    unique_classes: number
    unique_labels: string[]
    confidence_range: {
      min: number | null
      max: number | null
      mean: number | null
    }
    label_counts: Record<string, number>
  }
  bhava: {
    unique_classes: number
    unique_labels: string[]
    confidence_range: {
      min: number | null
      max: number | null
      mean: number | null
    }
    label_counts: Record<string, number>
  }
}

/** Time-based segment where consecutive frames have same predictions */
export interface TimeSegment {
  mudra: string | null
  mudra_confidence: number | null
  bhava: string | null
  bhava_confidence: number | null
  start_timestamp: number
  end_timestamp: number
  first_frame_number: number
  last_frame_number: number
  frame_count: number
}

/** Segmented analysis grouping consecutive frames with same predictions */
export interface TimeSegmentAnalysisResponse {
  video_id: string
  segment_count: number
  segments: TimeSegment[]
}

/* ------------------------------------------------------------------ */
/* API error shape                                                      */
/* ------------------------------------------------------------------ */

export interface ApiErrorPayload {
  message: string
  status?: number
  code?: string
}
