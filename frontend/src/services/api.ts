import axios, { AxiosError } from 'axios'
import type {
  AnalysisResult,
  AnalysisStatus,
  ApiErrorPayload,
  BhavaClassificationResponse,
  FusionResult,
  MudraClassificationResponse,
  MultilingualStory,
  StoryInterpretation,
  NarrativeGenerationResponse,
  TechnicalAudioEvidence,
  PerformanceInterpretationPackage,
  NarrativeEvidenceReviewSummary,
  CanonicalAnalysis,
  SupportedLanguage,
  FrameLevelAnalysisResponse,
  FrameAnalysisSummary,
  TimeSegmentAnalysisResponse,
} from '@/types/analysis'

/**
 * All communication with the Python AI backend is centralized here.
 * Nothing in this file fabricates data — every function either returns
 * what the backend sent, or throws a normalized ApiErrorPayload.
 *
 * The exact backend routes are expected to evolve during development;
 * keep the route strings in one place (ENDPOINTS) so they're easy to
 * update without touching call sites.
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

// A 4K, two-minute upload creates about 126 sampled JPEGs. On the project
// machine extraction has already exceeded five minutes, so 60 seconds aborts
// a healthy synchronous request before its manifest can be persisted.
const DEFAULT_TIMEOUT_MS = 60_000
const FRAME_EXTRACTION_TIMEOUT_MS = 15 * 60_000
const MODEL_INFERENCE_TIMEOUT_MS = 15 * 60_000
const CONSOLIDATION_TIMEOUT_MS = 2 * 60_000

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
})

const ENDPOINTS = {
  upload: () => '/api/upload',
  extractFrames: (videoId: string) => `/api/videos/${videoId}/frames`,
  analyze: () => '/api/analyze',
  analysis: (id: string) => `/api/analysis/${id}`,
  analysisStatus: (id: string) => `/api/analysis/${id}/status`,
  analysisResult: (id: string) => `/api/analysis/${id}/result`,
  mudra: (videoId: string) => `/api/videos/${videoId}/mudras`,
  bhava: (videoId: string) => `/api/videos/${videoId}/bhavas`,
  fusion: (videoId: string) => `/api/videos/${videoId}/fusion`,
  story: (videoId: string) => `/api/videos/${videoId}/story`,
  narrativeEvidence: (videoId: string) => `/api/videos/${videoId}/narrative-evidence`,
  narrativeEvidenceCandidates: (videoId: string) => `/api/videos/${videoId}/narrative-evidence/candidates`,
  narrativeEvidenceDraft: (videoId: string, evidenceId: string) => `/api/videos/${videoId}/narrative-evidence/${evidenceId}`,
  narrativeEvidenceSubmit: (videoId: string, evidenceId: string) => `/api/videos/${videoId}/narrative-evidence/${evidenceId}/submit`,
  narrativeEvidenceReview: (videoId: string, evidenceId: string) => `/api/videos/${videoId}/narrative-evidence/${evidenceId}/review`,
  demonstrationStory: () => '/api/demonstration/story',
  modalityResult: (videoId: string, modality: string) => `/api/videos/${videoId}/results/${modality}`,
  frameImage: (videoId: string, frameFilename: string) => `/api/videos/${videoId}/frames/${frameFilename}`,
  frameLevelAnalysis: (videoId: string) => `/api/videos/${videoId}/analysis/frames`,
  frameLevelAnalysisSummary: (videoId: string) => `/api/videos/${videoId}/analysis/frames/summary`,
  timeSegments: (videoId: string) => `/api/videos/${videoId}/analysis/frames/segments`,
}

export interface VideoUploadResponse {
  status: string
  video_id: string
  filename: string
  metadata: Record<string, unknown>
}

export interface ExtractedFrame {
  frame_number: number
  timestamp: number
  filename: string
}

export interface FrameExtractionResponse {
  video_id: string
  sampling_interval: number
  frame_count: number
  frames: ExtractedFrame[]
}

/** Normalizes any axios/network failure into a predictable shape the UI can render. */
function normalizeError(error: unknown): ApiErrorPayload {
  if (axios.isAxiosError(error)) {
    const err = error as AxiosError<{ message?: string; detail?: string }>

    if (err.response) {
      const backendMessage = err.response.data?.message ?? err.response.data?.detail
      return {
        message: backendMessage || `The backend returned an error (${err.response.status}).`,
        status: err.response.status,
        code: 'BACKEND_ERROR',
      }
    }

    if (err.code === 'ECONNABORTED') {
      return {
        message: 'The request to the HI-Natya Verse AI backend timed out.',
        code: 'TIMEOUT',
      }
    }

    return {
      message: 'Cannot connect to the HI-Natya Verse AI backend. Check that it is running and reachable.',
      code: 'NETWORK_ERROR',
    }
  }

  return {
    message: 'Something unexpected happened while talking to the backend.',
    code: 'UNKNOWN_ERROR',
  }
}

/** Uploads a video file to the FastAPI upload endpoint. */
export async function uploadVideo(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<VideoUploadResponse> {
  try {
    const formData = new FormData()
    formData.append('video', file)

    const response = await client.post<VideoUploadResponse>(ENDPOINTS.upload(), formData, {
      // Do not set Content-Type here: the browser adds the multipart boundary.
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    })

    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Extracts sampled frames from a video that was previously uploaded. */
export async function extractVideoFrames(
  videoId: string,
  samplingInterval: number,
): Promise<FrameExtractionResponse> {
  try {
    const response = await client.post<FrameExtractionResponse>(
      ENDPOINTS.extractFrames(videoId),
      { sampling_interval: samplingInterval },
      { timeout: FRAME_EXTRACTION_TIMEOUT_MS },
    )
    return response.data
  } catch (error) {
    throw normalizeStageError(error, 'Frame extraction')
  }
}

/** Uploads a performance video and starts analysis. Returns the new analysis id. */
export async function uploadPerformance(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ analysis_id: string }> {
  try {
    const formData = new FormData()
    formData.append('video', file)

    const response = await client.post<{ analysis_id: string }>(ENDPOINTS.analyze(), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    })

    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/**
 * Alias kept for backends that treat "upload" and "start analysis" as a
 * single call. Points at the same endpoint as uploadPerformance so either
 * name can be used from components without duplicating logic.
 */
export const startAnalysis = uploadPerformance

/** Polls the lightweight status endpoint (recommended for frequent polling). */
export async function getAnalysisStatus(analysisId: string): Promise<AnalysisStatus> {
  try {
    const response = await client.get<AnalysisStatus>(ENDPOINTS.analysisStatus(analysisId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Fetches the full multimodal analysis result once processing is complete. */
export async function getAnalysisResult(analysisId: string): Promise<AnalysisResult> {
  try {
    const response = await client.get<AnalysisResult>(ENDPOINTS.analysisResult(analysisId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

function normalizeStageError(error: unknown, stage: string): ApiErrorPayload {
  const normalized = normalizeError(error)
  return normalized.code === 'TIMEOUT'
    ? { ...normalized, message: `${stage} is taking longer than expected. Please wait while the backend completes the analysis.` }
    : normalized
}

/** Reads a previously generated modality artifact; it never starts inference. */
export async function getModalityResult<T>(videoId: string, modality: 'mudra' | 'bhava' | 'fusion' | 'story' | 'audio_evidence' | 'performance_interpretation'): Promise<T> {
  try {
    const response = await client.get<T>(ENDPOINTS.modalityResult(videoId, modality))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Loads all persisted results for one video into the frontend's canonical analysis object. */
export async function getCanonicalAnalysis(videoId: string): Promise<CanonicalAnalysis> {
  const [mudra, bhava, fusion, audioEvidence, performanceInterpretation, narrativeEvidenceReview] = await Promise.all([
    getModalityResult<MudraClassificationResponse>(videoId, 'mudra'),
    getModalityResult<BhavaClassificationResponse>(videoId, 'bhava'),
    getModalityResult<FusionResult>(videoId, 'fusion'),
    getModalityResult<TechnicalAudioEvidence>(videoId, 'audio_evidence').catch((error: ApiErrorPayload) => {
      if (error.status === 404) return null
      throw error
    }),
    getModalityResult<PerformanceInterpretationPackage>(videoId, 'performance_interpretation').catch((error: ApiErrorPayload) => {
      if (error.status === 404) return null
      throw error
    }),
    getNarrativeEvidenceReview(videoId).catch((error: ApiErrorPayload) => {
      if (error.status === 404) return null
      throw error
    }),
  ])
  return { videoId, mudra, bhava, fusion, audioEvidence, performanceInterpretation, narrativeEvidenceReview: narrativeEvidenceReview as NarrativeEvidenceReviewSummary | null }
}

/** Runs Mudra classification on extracted frames. */
export async function classifyMudras(videoId: string): Promise<MudraClassificationResponse> {
  try {
    const response = await client.post<MudraClassificationResponse>(ENDPOINTS.mudra(videoId), undefined, {
      timeout: MODEL_INFERENCE_TIMEOUT_MS,
    })
    return response.data
  } catch (error) {
    throw normalizeStageError(error, 'Mudra analysis')
  }
}

/** Runs Bhava classification on extracted frames. */
export async function classifyBhavas(videoId: string): Promise<BhavaClassificationResponse> {
  try {
    const response = await client.post<BhavaClassificationResponse>(ENDPOINTS.bhava(videoId), undefined, {
      timeout: MODEL_INFERENCE_TIMEOUT_MS,
    })
    return response.data
  } catch (error) {
    throw normalizeStageError(error, 'Bhava analysis')
  }
}

/** Fuses mudra and bhava results with timestamp alignment. */
export async function fuse(videoId: string): Promise<FusionResult> {
  try {
    const response = await client.post<FusionResult>(ENDPOINTS.fusion(videoId), undefined, {
      timeout: CONSOLIDATION_TIMEOUT_MS,
    })
    return response.data
  } catch (error) {
    throw normalizeStageError(error, 'Fusion')
  }
}

/** Generates evidence-grounded story in the specified language. */
export async function generateStory(
  videoId: string,
  language?: string | SupportedLanguage,
): Promise<NarrativeGenerationResponse> {
  try {
    const response = await client.post<NarrativeGenerationResponse>(ENDPOINTS.story(videoId), {
      language: language || 'en',
    }, { timeout: CONSOLIDATION_TIMEOUT_MS })
    return response.data
  } catch (error) {
    throw normalizeStageError(error, 'Story generation')
  }
}

/** Fetches the generated story/interpretation in a given language. */
export async function getStory(
  analysisId: string,
  language?: SupportedLanguage | string,
): Promise<StoryInterpretation> {
  try {
    const response = await client.get<StoryInterpretation>(ENDPOINTS.story(analysisId), {
      params: language ? { language } : undefined,
    })
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Fetches every language variant of the story at once, if the backend supports it. */
export async function getMultilingualStory(analysisId: string): Promise<MultilingualStory> {
  try {
    const response = await client.get<MultilingualStory>(ENDPOINTS.story(analysisId), {
      params: { all_languages: true },
    })
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

export type NarrativeEvidenceStatus = 'draft' | 'submitted' | 'verified' | 'rejected'

export interface NarrativeEvidenceReviewRecord {
  evidence_id: string
  statement: string
  statement_type: string
  source_reference: string
  submitted_by: string
  submitted_at: string
  span: { start_time: number; end_time: number } | null
  status: NarrativeEvidenceStatus
  verified_by: string | null
  verified_at: string | null
  production_eligibility: { status: 'eligible' | 'ineligible' }
  review_reason: string | null
  performance_mode: 'pure_dance' | 'narrative_dance' | 'unknown'
  candidate_origin: 'human_submitted' | 'ai_assisted'
}

/** Reads a cached Story only; it never starts Gemini generation. */
export async function getGeneratedStory(videoId: string, language: string = 'en'): Promise<NarrativeGenerationResponse> {
  try {
    return (await client.get<NarrativeGenerationResponse>(ENDPOINTS.story(videoId), {
      params: { language },
    })).data
  } catch (error) {
    throw normalizeError(error)
  }
}

export interface DemonstrationStoryResponse {
  demonstration: true
  analysis_id: string
  title: string
  notice: string
  story: NarrativeGenerationResponse
  evidence_used: Array<{ event_id: string; statement: string; type: string }>
}

/** Loads the isolated synthetic demonstration; it never addresses a real analysis. */
export async function generateDemonstrationStory(): Promise<DemonstrationStoryResponse> {
  try {
    return (await client.post<DemonstrationStoryResponse>(ENDPOINTS.demonstrationStory())).data
  } catch (error) {
    throw normalizeError(error)
  }
}

export interface NarrativeEvidenceReview {
  analysis_id: string
  video_id: string
  records: NarrativeEvidenceReviewRecord[]
  story_eligible: boolean
  story_eligibility_reason: string
}

export interface NarrativeEvidenceSubmission {
  analysis_id: string
  video_id: string
  statement: string
  statement_type: 'verified_narrative_event' | 'verified_performance_event'
  source_reference: string
  submitted_by: string
  verification_method: string
  verification_confidence: number
  span: { start_time: number; end_time: number } | null
  provenance: { type: 'curated_annotation' | 'expert_verification' | 'trusted_source_annotation'; reference: string }
  performance_mode: 'pure_dance' | 'narrative_dance'
  status: 'draft' | 'submitted'
}

export interface NarrativeEvidenceDecision {
  status: 'verified' | 'rejected'
  verified_by: string
  verification_method: string
  verification_confidence: number
  production_eligible: boolean
  review_reason: string
}

export async function getNarrativeEvidenceReview(videoId: string): Promise<NarrativeEvidenceReview> {
  try {
    return (await client.get<NarrativeEvidenceReview>(ENDPOINTS.narrativeEvidence(videoId))).data
  } catch (error) {
    throw normalizeError(error)
  }
}

export async function submitNarrativeEvidence(videoId: string, submission: NarrativeEvidenceSubmission): Promise<void> {
  try {
    await client.post(ENDPOINTS.narrativeEvidence(videoId), submission)
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Creates AI-assisted drafts from the completed persisted analysis summary. */
export async function prepareNarrativeEvidenceCandidates(videoId: string): Promise<NarrativeEvidenceReviewRecord[]> {
  try {
    return (await client.post<{ candidates: NarrativeEvidenceReviewRecord[] }>(ENDPOINTS.narrativeEvidenceCandidates(videoId))).data.candidates
  } catch (error) {
    throw normalizeError(error)
  }
}

/** A draft can be corrected by a human before it enters the reviewer queue. */
export async function updateNarrativeEvidenceDraft(videoId: string, evidenceId: string, draft: { statement: string; performance_mode: 'pure_dance' | 'narrative_dance' | 'unknown' }): Promise<void> {
  try {
    await client.patch(ENDPOINTS.narrativeEvidenceDraft(videoId, evidenceId), draft)
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Moves a curator draft into the persisted reviewer queue. */
export async function submitNarrativeEvidenceForReview(videoId: string, evidenceId: string): Promise<void> {
  try {
    await client.post(ENDPOINTS.narrativeEvidenceSubmit(videoId, evidenceId))
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Records an explicit reviewer decision; it never derives verification from AI output. */
export async function reviewNarrativeEvidence(videoId: string, evidenceId: string, decision: NarrativeEvidenceDecision): Promise<void> {
  try {
    await client.post(ENDPOINTS.narrativeEvidenceReview(videoId, evidenceId), decision)
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Get frame-level analysis for a video. */
export async function getFrameLevelAnalysis(videoId: string): Promise<FrameLevelAnalysisResponse> {
  try {
    const response = await client.get<FrameLevelAnalysisResponse>(ENDPOINTS.frameLevelAnalysis(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Get summary statistics for frame-level analysis. */
export async function getFrameAnalysisSummary(videoId: string): Promise<FrameAnalysisSummary> {
  try {
    const response = await client.get<FrameAnalysisSummary>(ENDPOINTS.frameLevelAnalysisSummary(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Get time-based segments where consecutive frames have the same predictions. */
export async function getTimeSegments(videoId: string): Promise<TimeSegmentAnalysisResponse> {
  try {
    const response = await client.get<TimeSegmentAnalysisResponse>(ENDPOINTS.timeSegments(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Get the URL for a frame image. */
export function getFrameImageUrl(videoId: string, frameFilename: string): string {
  return `${API_BASE_URL}${ENDPOINTS.frameImage(videoId, frameFilename)}`
}
