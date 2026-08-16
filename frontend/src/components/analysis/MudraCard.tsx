import type { MudraDetection } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface MudraCardProps {
  mudra: MudraDetection
}

export default function MudraCard({ mudra }: MudraCardProps) {
  return (
    <div className="card-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <h4 className="font-display text-xl text-espresso">{mudra.name}</h4>
        <GroundingBadge status={mudra.grounded ? 'grounded' : 'unresolved'} size="sm" />
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-xs uppercase tracking-wide text-espresso-faint">Meaning</p>
        {mudra.grounded ? (
          <p className="text-sm text-espresso">{mudra.meaning ?? '—'}</p>
        ) : (
          <p className="text-sm italic text-espresso-faint">Unavailable in current knowledge base</p>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-4 text-xs text-espresso-faint">
        <span>{formatPercent(mudra.confidence) ?? 'Confidence pending'}</span>
        {mudra.occurrence_count !== undefined && <span>{mudra.occurrence_count}× detected</span>}
      </div>
    </div>
  )
}
