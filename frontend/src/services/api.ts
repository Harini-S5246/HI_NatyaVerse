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
  StoryResponse,
  SupportedLanguage,
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60_000,
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
    const response = await client.post<FrameExtractionResponse>(ENDPOINTS.extractFrames(videoId), {
      sampling_interval: samplingInterval,
    })
    return response.data
  } catch (error) {
    throw normalizeError(error)
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

/** Runs Mudra classification on extracted frames. */
export async function classifyMudras(videoId: string): Promise<MudraClassificationResponse> {
  try {
    const response = await client.post<MudraClassificationResponse>(ENDPOINTS.mudra(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Runs Bhava classification on extracted frames. */
export async function classifyBhavas(videoId: string): Promise<BhavaClassificationResponse> {
  try {
    const response = await client.post<BhavaClassificationResponse>(ENDPOINTS.bhava(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Fuses mudra and bhava results with timestamp alignment. */
export async function fuse(videoId: string): Promise<FusionResult> {
  try {
    const response = await client.post<FusionResult>(ENDPOINTS.fusion(videoId))
    return response.data
  } catch (error) {
    throw normalizeError(error)
  }
}

/** Generates evidence-grounded story in the specified language. */
export async function generateStory(
  videoId: string,
  language?: string | SupportedLanguage,
): Promise<StoryResponse> {
  try {
    const response = await client.post<StoryResponse>(ENDPOINTS.story(videoId), {
      language: language || 'en',
    })
    return response.data
  } catch (error) {
    throw normalizeError(error)
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

export { API_BASE_URL }
