import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import StoryPanel from '@/components/story/StoryPanel'
import LanguageSelector from '@/components/LanguageSelector'
import LoadingState from '@/components/common/LoadingState'
import ErrorMessage from '@/components/common/ErrorMessage'
import EmptyState from '@/components/common/EmptyState'
import { generateStory, getGeneratedStory } from '@/services/api'
import type { ApiErrorPayload, NarrativeGenerationResponse, SupportedLanguage } from '@/types/analysis'

interface StoryProps { language: SupportedLanguage; onLanguageChange: (language: SupportedLanguage) => void }

const LANGUAGE_CODE_MAP: Record<SupportedLanguage, string> = {
  English: 'en', Tamil: 'ta', Hindi: 'hi', Malayalam: 'ml', Telugu: 'te', Kannada: 'kn', Bengali: 'bn',
}

export default function Story({ language, onLanguageChange }: StoryProps) {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [story, setStory] = useState<NarrativeGenerationResponse | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const requestSequence = useRef(0)
  const generating = useRef(false)

  const load = async () => {
    if (!analysisId) return
    const requestId = ++requestSequence.current
    setLoading(true); setError(null); setStory(null)
    try {
      const response = await getGeneratedStory(analysisId, LANGUAGE_CODE_MAP[language])
      if (requestId === requestSequence.current) setStory(response)
    } catch (err) {
      if (requestId === requestSequence.current) setError(err as ApiErrorPayload)
    } finally {
      if (requestId === requestSequence.current) setLoading(false)
    }
  }

  const generate = async () => {
    if (!analysisId || generating.current) return
    generating.current = true
    console.info('[STORY_GENERATE_CLICKED]', { analysis_id: analysisId, package_fingerprint: story?.package_fingerprint ?? null })
    const requestId = ++requestSequence.current
    setLoading(true); setError(null)
    try {
      const response = await generateStory(analysisId, LANGUAGE_CODE_MAP[language] ?? 'en')
      if (requestId === requestSequence.current) setStory(response)
      if (response.status === 'generated') await load()
    } catch (err) {
      if (requestId === requestSequence.current) setError(err as ApiErrorPayload)
    } finally {
      if (requestId === requestSequence.current) setLoading(false)
      generating.current = false
    }
  }

  useEffect(() => {
    void load()
    return () => { requestSequence.current += 1 }
    // The route ID and selected language are the full request identity.
  }, [analysisId, language])

  if (!analysisId) return <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10"><EmptyState title="No performance analyzed yet." description="Upload a Bharatanatyam performance to view its evidence-grounded interpretation." actionLabel="Analyze a Performance" actionTo="/analyze" /></div>
  return (
    <div className="mx-auto max-w-5xl px-6 py-12 lg:px-10">
      <div className="flex flex-wrap items-start justify-between gap-6"><p className="eyebrow">Step 3 of 3 · Interpretation language</p><LanguageSelector value={language} onChange={onLanguageChange} variant="panel" /></div>
      <div className="mt-8">
        {loading && <LoadingState label={generating.current ? 'Generating Story…' : 'Requesting the verified performance interpretation…'} />}
        {!loading && error && <ErrorMessage error={error} onRetry={load} />}
        {!loading && !error && story && <StoryPanel story={story} />}
        {!loading && !error && story?.status !== 'generated' && <div className="mt-6 border border-line bg-card-surface p-5"><p className="text-sm text-espresso-light">{story?.package_eligible ? (story.message ?? 'Your verified evidence is ready.') : 'No verified narrative evidence available.'}</p>{story?.package_eligible && <button type="button" onClick={() => void generate()} className="btn-primary mt-3">{story.status === 'retryable' ? 'Retry Generate Story' : 'Generate Story'}</button>}{!story?.package_eligible && <Link to={`/analysis/${analysisId}#narrative-evidence-heading`} className="mt-3 inline-flex text-sm font-medium text-espresso underline underline-offset-4">Review Evidence for Story</Link>}</div>}
        {!loading && !error && !story && <EmptyState title="No interpretation available." description="The backend did not return a validated narrative response." />}
      </div>
    </div>
  )
}
