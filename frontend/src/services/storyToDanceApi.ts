import axios from 'axios'
import { client } from '@/services/api'
import type {
  DanceGenerationResult,
  SceneVisualReferenceRequest,
  SceneVisualReferences,
  StoryToDanceRecord,
  StoryToDanceWorkflowResponse,
} from '@/types/storyToDance'

const ENDPOINT = '/api/story-to-dance/stories'

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as {
      message?: unknown
      detail?: unknown
      code?: unknown
      scene_ids?: unknown
    } | undefined
    if (typeof payload?.message === 'string') return payload.message
    if (typeof payload?.detail === 'string') return payload.detail
    if (Array.isArray(payload?.detail)) {
      return `The Story-to-Dance request was rejected: ${JSON.stringify(payload.detail)}`
    }
    if (!error.response) {
      return (
        `Could not reach the Story-to-Dance API at ${client.defaults.baseURL ?? 'its configured address'}`
        + ` (${error.code ?? 'network error'}). Check that the backend is running and accessible from this browser.`
      )
    }
    if (typeof payload?.code === 'string') {
      const sceneIds = Array.isArray(payload.scene_ids)
        ? ` Scenes: ${payload.scene_ids.join(', ')}.`
        : ''
      return `Story-to-Dance API error (${payload.code}).${sceneIds}`
    }
    return `Story-to-Dance API request failed with HTTP ${error.response.status}.`
  }
  return error instanceof Error ? error.message : 'The Story-to-Dance service could not complete the request.'
}

async function request<T>(operation: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await operation()).data
  } catch (error) {
    throw new Error(errorMessage(error))
  }
}

export function createStoryToDanceStory(
  storyText: string,
  language: string,
  title?: string,
): Promise<StoryToDanceRecord> {
  return request(() =>
    client.post<StoryToDanceRecord>(ENDPOINT, {
      story_text: storyText,
      language,
      title,
    }),
  )
}

export function generateStoryToDanceWorkflow(
  storyText: string,
  language: string,
  requestId: string,
  title?: string,
): Promise<StoryToDanceWorkflowResponse> {
  return request(() =>
    client.post<StoryToDanceWorkflowResponse>(
      `${ENDPOINT}/workflow`,
      {
        story_text: storyText,
        language,
        request_id: requestId,
        title,
      },
      { timeout: 15 * 60_000 },
    ),
  )
}

export function getStoryToDanceWorkflow(
  requestId: string,
): Promise<StoryToDanceWorkflowResponse> {
  return request(() =>
    client.get<StoryToDanceWorkflowResponse>(
      `${ENDPOINT}/workflow/${encodeURIComponent(requestId)}`,
      { timeout: 15 * 60_000 },
    ),
  )
}

export function generateStoryToDancePlan(storyId: string): Promise<StoryToDanceRecord> {
  return request(() =>
    client.post<StoryToDanceRecord>(`${ENDPOINT}/${encodeURIComponent(storyId)}/plan`),
  )
}

const visualReferenceRequests = new Map<string, Promise<SceneVisualReferences[]>>()

export function getStoryToDanceVisualReferences(
  scenes: SceneVisualReferenceRequest[],
): Promise<SceneVisualReferences[]> {
  const key = JSON.stringify(scenes)
  const cached = visualReferenceRequests.get(key)
  if (cached) return cached

  const pending = request(() =>
    client.post<SceneVisualReferences[]>(
      `${ENDPOINT}/visual-references`,
      { scenes },
    ),
  )
  visualReferenceRequests.set(key, pending)
  void pending.catch(() => visualReferenceRequests.delete(key))
  return pending
}

export function getStoryToDanceStory(storyId: string): Promise<StoryToDanceRecord> {
  return request(() =>
    client.get<StoryToDanceRecord>(`${ENDPOINT}/${encodeURIComponent(storyId)}`),
  )
}

export function generateStoryToDancePerformance(
  storyId: string,
  dancePlanId: string,
): Promise<DanceGenerationResult> {
  return request(() =>
    client.post<DanceGenerationResult>(
      `${ENDPOINT}/${encodeURIComponent(storyId)}/plans/${encodeURIComponent(dancePlanId)}/performance`,
      undefined,
      { timeout: 15 * 60_000 },
    ),
  )
}
