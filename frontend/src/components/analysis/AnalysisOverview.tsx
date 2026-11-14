import type { CanonicalAnalysis } from '@/types/analysis'
import { formatDuration } from '@/utils/format'

interface AnalysisOverviewProps {
  analysis: CanonicalAnalysis
}

export default function AnalysisOverview({ analysis }: AnalysisOverviewProps) {
  const { fusion, videoId } = analysis
  const evidence = fusion.evidence
  const duration = fusion.timeline.length ? Math.max(...fusion.timeline.map((item) => item.end_time)) : undefined
  const hasGrounded = evidence.grounded.length > 0
  const hasDetected = evidence.detected.length > 0
  const hasUnresolved = evidence.unresolved.length > 0
  const evidenceStatus = hasGrounded || hasDetected
    ? 'Analysis evidence available'
    : hasUnresolved
      ? 'Unresolved observations reported'
      : 'No evidence available'

  return (
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <div className="card-surface p-8">
        <p className="eyebrow">Performance</p>
        <h2 className="mt-2 font-display text-3xl text-espresso">Performance Analysis</h2>
        <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-3">
          <div><dt className="text-xs uppercase tracking-wide text-espresso-faint">Status</dt><dd className="mt-1 text-sm text-espresso">{fusion.status}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-espresso-faint">Duration</dt><dd className="mt-1 text-sm text-espresso">{formatDuration(duration) ?? '—'}</dd></div>
          <div><dt className="text-xs uppercase tracking-wide text-espresso-faint">Analysis ID</dt><dd className="mt-1 truncate text-sm text-espresso" title={videoId}>{videoId}</dd></div>
        </dl>
        <p className="mt-5 text-xs text-espresso-faint">Frames analyzed: {fusion.summary.frame_count}</p>
      </div>
      <div className="card-surface p-6">
        <p className="eyebrow">Overall Evidence</p>
        <p className="mt-3 font-display text-2xl text-espresso">{evidenceStatus}</p>
        <p className="mt-3 text-sm text-espresso-light">{hasUnresolved ? `${evidence.unresolved.length} unresolved observation${evidence.unresolved.length === 1 ? '' : 's'} are not promoted into narrative claims.` : 'No unresolved observations reported.'}</p>
        <p className="mt-2 text-xs text-espresso-faint">Fusion status: {fusion.status}</p>
      </div>
    </div>
  )
}
