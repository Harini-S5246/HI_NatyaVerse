import { useCallback, useState } from 'react'

const STORAGE_KEY = 'hi-natya-verse:last-analysis-id'

function read(): string | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(STORAGE_KEY)
}

export function useLastAnalysisId() {
  const [lastAnalysisId, setLastAnalysisIdState] = useState<string | null>(read)

  const setLastAnalysisId = useCallback((id: string) => {
    window.sessionStorage.setItem(STORAGE_KEY, id)
    setLastAnalysisIdState(id)
  }, [])

  return { lastAnalysisId, setLastAnalysisId }
}
