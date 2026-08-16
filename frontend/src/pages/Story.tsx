import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import StoryPanel from '@/components/story/StoryPanel'
import InterpretationPanel from '@/components/story/InterpretationPanel'
import LanguageSelector from '@/components/LanguageSelector'
import LoadingState from '@/components/common/LoadingState'
import ErrorMessage from '@/components/common/ErrorMessage'
import EmptyState from '@/components/common/EmptyState'
import { generateStory, getAnalysisResult } from '@/services/api'
import { deriveEvidence } from '@/utils/evidence'
import type { AnalysisResult, ApiErrorPayload, StoryResponse, SupportedLanguage } from '@/types/analysis'

interface StoryProps {
  language: SupportedLanguage
  onLanguageChange: (language: SupportedLanguage) => void
}

export default function Story({ language, onLanguageChange }: StoryProps) {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [story, setStory] = useState<StoryResponse | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    if (!analysisId) return
    setLoading(true)
    setError(null)
    try {
      // Map frontend language names to backend codes
      const langCode = language === 'Tamil' ? 'ta' : 'en'
      
      const [storyData, resultData] = await Promise.all([
        generateStory(analysisId, langCode),
        result ? Promise.resolve(result) : getAnalysisResult(analysisId).catch(() => null),
      ])
      setStory(storyData)
      if (resultData) setResult(resultData)
    } catch (err) {
      setError(err as ApiErrorPayload)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, language])

  if (!analysisId) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10">
        <EmptyState
          title="No performance analyzed yet."
          description="Upload a Bharatanatyam performance to generate its story here."
          actionLabel="Analyze a Performance"
          actionTo="/analyze"
        />
      </div>
    )
  }

  const evidence = deriveEvidence(result)

  return (
    <div className="mx-auto max-w-6xl px-6 py-16 lg:px-10">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <p className="eyebrow">Step 3 of 3 · Interpretation Language</p>
        <LanguageSelector value={language} onChange={onLanguageChange} variant="panel" />
      </div>

      <div className="mt-8">
        {loading && <LoadingState label="Generating story…" />}

        {!loading && error && <ErrorMessage error={error} onRetry={load} />}

        {!loading && !error && story && (
          <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
            <StoryPanel story={story} />
            <InterpretationPanel evidence={evidence} result={result} />
          </div>
        )}

        {!loading && !error && !story && (
          <EmptyState
            title="No story available yet."
            description="The backend has not generated an interpretation for this performance yet."
          />
        )}
      </div>
    </div>
  )
}
