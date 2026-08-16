import type { AnalysisResult } from '@/types/analysis'
import { formatDuration } from '@/utils/format'
import ConfidenceCard from '@/components/analysis/ConfidenceCard'

interface AnalysisOverviewProps {
  result: AnalysisResult
}

export default function AnalysisOverview({ result }: AnalysisOverviewProps) {
  const { performance } = result

  return (
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <div className="card-surface p-8">
        <p className="eyebrow">Performance</p>
        <h2 className="mt-2 font-display text-3xl text-espresso">
          {performance?.performance_name ?? 'Untitled performance'}
        </h2>

        <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-espresso-faint">Type</dt>
            <dd className="mt-1 text-sm text-espresso">{performance?.performance_type ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-espresso-faint">Duration</dt>
            <dd className="mt-1 text-sm text-espresso">
              {formatDuration(performance?.duration_seconds) ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-espresso-faint">Analysis ID</dt>
            <dd className="mt-1 truncate text-sm text-espresso" title={result.analysis_id}>
              {result.analysis_id}
            </dd>
          </div>
        </dl>
      </div>

      <ConfidenceCard
        label="Overall Evidence"
        score={result.overall_evidence_strength ?? result.confidence?.score}
        level={result.evidence_level ?? result.confidence?.level}
        helperText="Combined strength of grounded and detected evidence across all modalities."
      />
    </div>
  )
}
