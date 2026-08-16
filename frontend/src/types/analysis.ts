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

/* ------------------------------------------------------------------ */
/* Story / interpretation                                               */
/* ------------------------------------------------------------------ */

export interface StoryInterpretationItem {
  id: string
  statement: string
  supporting_evidence: string[]
  confidence?: number | null
  status: string
}

/**
 * Evidence-grounded story response from POST /api/videos/{video_id}/story.
 * Follows the deterministic template-based generation with curated meanings.
 */
export interface StoryResponse {
  analysis_id: string
  status: 'completed' | 'insufficient_grounded_evidence'
  language: string
  title: string | null
  story: string | null
  interpretations: StoryInterpretationItem[]
  supporting_evidence: string[]
  unresolved_evidence: string[]
  message: string | null
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
  label: string
  confidence: number
  grounded: boolean
  status: GroundingStatus
  meaning?: string | null
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
  label: string
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
  event_id: string
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
/* API error shape                                                      */
/* ------------------------------------------------------------------ */

export interface ApiErrorPayload {
  message: string
  status?: number
  code?: string
}
