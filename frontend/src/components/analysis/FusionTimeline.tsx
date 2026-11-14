import type { FusionTimelineRow } from '@/types/analysis'
import { formatDuration, formatPercent } from '@/utils/format'

interface FusionTimelineProps { timeline: FusionTimelineRow[] }

export default function FusionTimeline({ timeline }: FusionTimelineProps) {
  if (timeline.length === 0) return <p className="text-sm text-espresso-faint">No fusion timeline was reported by the backend.</p>
  return <div className="card-surface divide-y divide-line">{timeline.map((item, index) => (
    <div key={`${item.start_time}-${item.end_time}-${index}`} className="grid gap-4 p-6 sm:grid-cols-[150px_1fr_1fr]">
      <p className="text-sm text-espresso-light">{formatDuration(item.start_time)}–{formatDuration(item.end_time)}</p>
      <div><p className="eyebrow">Mudra</p><p className="mt-1 text-base text-espresso">{item.mudra ?? 'Not detected'}</p>{item.mudra && <p className="mt-1 text-xs text-espresso-faint">{formatPercent(item.mudra_confidence)}</p>}{item.mudra && <p className="mt-2 text-xs text-espresso-faint">{item.mudra_verification_status?.replaceAll('_', ' ') ?? 'Verification status unavailable'}</p>}{item.mudra_claim_id && <p className="mt-1 text-xs text-espresso-faint">Claim: {item.mudra_claim_id}</p>}{item.mudra_source_references?.map((reference) => <p key={reference} className="mt-1 text-xs text-espresso-faint">Source: {reference}</p>)}{item.mudra_uncertainty_notes?.map((note) => <p key={note} className="mt-1 text-xs text-espresso-faint">Uncertainty: {note}</p>)}</div>
      <div><p className="eyebrow">Facial-expression observation</p><p className="mt-1 text-base text-espresso">{item.bhava ?? 'Not detected'}</p>{item.bhava && <p className="mt-1 text-xs text-espresso-faint">{formatPercent(item.bhava_confidence)}</p>}</div>
    </div>
  ))}</div>
}
