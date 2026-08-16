import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import AnalysisOverview from '@/components/analysis/AnalysisOverview'
import MudraTable from '@/components/analysis/MudraTable'
import BhavaCard from '@/components/analysis/BhavaCard'
import PoseCard from '@/components/analysis/PoseCard'
import AudioCard from '@/components/analysis/AudioCard'
import EvidencePanel from '@/components/evidence/EvidencePanel'
import WhyInterpretation from '@/components/evidence/WhyInterpretation'
import SectionHeading from '@/components/common/SectionHeading'
import LoadingState from '@/components/common/LoadingState'
import ErrorMessage from '@/components/common/ErrorMessage'
import EmptyState from '@/components/common/EmptyState'
import { getAnalysisResult } from '@/services/api'
import { deriveEvidence } from '@/utils/evidence'
import type { AnalysisResult, ApiErrorPayload, SupportedLanguage } from '@/types/analysis'

interface AnalysisProps {
  language: SupportedLanguage
  onLanguageChange: (language: SupportedLanguage) => void
}

export default function Analysis({}: AnalysisProps) {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    if (!analysisId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getAnalysisResult(analysisId)
      setResult(data)
    } catch (err) {
      setError(err as ApiErrorPayload)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId])

  if (!analysisId) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10">
        <EmptyState
          title="No performance analyzed yet."
          description="Upload a Bharatanatyam performance to see its multimodal analysis here."
          actionLabel="Analyze a Performance"
          actionTo="/analyze"
        />
      </div>
    )
  }

  if (loading) {
    return <LoadingState label="Loading analysis…" />
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10">
        <ErrorMessage error={error} onRetry={load} />
      </div>
    )
  }

  if (!result) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10">
        <EmptyState
          title="No result found."
          description="This analysis could not be located on the backend."
          actionLabel="Analyze a Performance"
          actionTo="/analyze"
        />
      </div>
    )
  }

  const evidence = deriveEvidence(result)

  return (
    <div className="mx-auto max-w-6xl px-6 py-16 lg:px-10">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="eyebrow mb-3">Step 2 of 3</p>
          <h1 className="text-4xl text-espresso sm:text-5xl">Performance Insight</h1>
        </div>
        <Link to={`/story/${analysisId}`} className="btn-primary">
          <BookOpen className="h-4 w-4" aria-hidden="true" />
          View Story
        </Link>
      </div>

      <div className="mt-10">
        <AnalysisOverview result={result} />
      </div>

      <div className="mt-16">
        <SectionHeading eyebrow="Multimodal analysis" title="Mudra, Bhava, Pose &amp; Audio" />
        <div className="mt-8 grid gap-6 lg:grid-cols-3">
          <BhavaCard bhava={result.bhava} />
          <PoseCard pose={result.pose} />
          <AudioCard audio={result.audio} />
        </div>
      </div>

      <div className="mt-16">
        <SectionHeading
          eyebrow="Mudra analysis"
          title="Detected mudras"
          description="Grounded meanings come from the Bharatanatyam knowledge base; unresolved mudras are shown as unresolved rather than guessed at."
        />
        <div className="mt-8">
          <MudraTable mudras={result.mudra?.detections ?? []} />
        </div>
      </div>

      <div className="mt-16">
        <SectionHeading
          eyebrow="Evidence"
          title="Grounded, detected, interpreted &amp; unresolved"
          description="Every claim in the final story traces back to one of these evidence categories."
        />
        <div className="mt-8">
          <EvidencePanel evidence={evidence} />
        </div>
      </div>

      <div className="mt-16">
        <WhyInterpretation evidence={evidence} />
      </div>
    </div>
  )
}
