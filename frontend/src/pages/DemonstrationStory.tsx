import { useState } from 'react'
import StoryPanel from '@/components/story/StoryPanel'
import ErrorMessage from '@/components/common/ErrorMessage'
import LoadingState from '@/components/common/LoadingState'
import { generateDemonstrationStory, type DemonstrationStoryResponse } from '@/services/api'
import type { ApiErrorPayload } from '@/types/analysis'

export default function DemonstrationStory() {
  const [result, setResult] = useState<DemonstrationStoryResponse | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const load = async () => {
    setLoading(true); setError(null)
    try { setResult(await generateDemonstrationStory()) } catch (err) { setError(err as ApiErrorPayload) } finally { setLoading(false) }
  }
  return <div className="mx-auto max-w-5xl px-6 py-12 lg:px-10">
    <p className="eyebrow">Demonstration Fixture</p>
    <h1 className="mt-3 font-display text-4xl text-espresso sm:text-5xl">Demonstration / Sample Verified Performance</h1>
    <p className="mt-4 max-w-3xl text-sm leading-relaxed text-espresso-light">This story is generated from explicitly verified demonstration evidence and is not an interpretation of a real uploaded performance.</p>
    <div className="mt-8">{loading && <LoadingState label="Requesting the verified demonstration story…" />}{!loading && error && <ErrorMessage error={error} onRetry={load} />}{!loading && !error && !result && <button type="button" onClick={() => void load()} className="btn-primary">Generate Demonstration Story</button>}{!loading && result && <StoryPanel story={result.story} demonstration evidenceUsed={result.evidence_used} />}</div>
  </div>
}
