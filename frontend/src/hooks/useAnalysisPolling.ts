import { useEffect, useRef, useState } from 'react'
import { getAnalysisStatus } from '@/services/api'
import type { AnalysisStatus, ApiErrorPayload } from '@/types/analysis'

interface UseAnalysisPollingOptions {
  intervalMs?: number
  enabled?: boolean
}

interface UseAnalysisPollingResult {
  status: AnalysisStatus | null
  error: ApiErrorPayload | null
  isComplete: boolean
  isFailed: boolean
}

/**
 * Polls GET /api/analysis/{id}/status on an interval until the backend
 * reports "completed" or "failed". Stops polling in either case, or if
 * the request fails outright (e.g. backend unreachable).
 */
export function useAnalysisPolling(
  analysisId: string | null,
  { intervalMs = 3000, enabled = true }: UseAnalysisPollingOptions = {},
): UseAnalysisPollingResult {
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!analysisId || !enabled) return

    let cancelled = false

    const poll = async () => {
      try {
        const result = await getAnalysisStatus(analysisId)
        if (cancelled) return
        setStatus(result)
        setError(null)

        if (result.status !== 'completed' && result.status !== 'failed') {
          timerRef.current = setTimeout(poll, intervalMs)
        }
      } catch (err) {
        if (cancelled) return
        setError(err as ApiErrorPayload)
      }
    }

    poll()

    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [analysisId, enabled, intervalMs])

  return {
    status,
    error,
    isComplete: status?.status === 'completed',
    isFailed: status?.status === 'failed',
  }
}
