import { Smile } from 'lucide-react'
import type { BhavaAnalysis } from '@/types/analysis'
import { formatDuration, formatPercent } from '@/utils/format'

interface BhavaCardProps {
  bhava?: BhavaAnalysis
}

export default function BhavaCard({ bhava }: BhavaCardProps) {
  if (!bhava || (!bhava.dominant_emotion && (!bhava.segments || bhava.segments.length === 0))) {
    return (
      <div className="card-surface p-6">
        <p className="eyebrow">Facial-expression observations</p>
        <p className="mt-4 text-sm text-espresso-faint">No bhava analysis was reported by the backend.</p>
      </div>
    )
  }

  return (
    <div className="card-surface p-6">
      <div className="flex items-center justify-between">
        <p className="eyebrow">Facial-expression observations</p>
        <Smile className="h-4 w-4 text-vermilion-500" aria-hidden="true" />
      </div>

      {bhava.dominant_emotion && (
        <>
          <p className="mt-3 font-display text-3xl text-espresso">{bhava.dominant_emotion}</p>
          <p className="mt-1 text-xs text-espresso-faint">Most common predicted emotion label</p>
          <p className="mt-3 text-sm text-espresso-light">
            {formatPercent(bhava.confidence ?? bhava.bhava_confidence) ?? 'Confidence pending'}
          </p>
        </>
      )}

      {bhava.segments && bhava.segments.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-xs uppercase tracking-wide text-espresso-faint">Segments</p>
          <ul className="mt-2 space-y-2">
            {bhava.segments.map((segment, index) => (
              <li key={`${segment.label}-${index}`} className="flex items-center justify-between text-sm">
                <span className="text-espresso">{segment.label}</span>
                <span className="text-espresso-faint">
                  {segment.start !== undefined && segment.end !== undefined
                    ? `${formatDuration(segment.start)}–${formatDuration(segment.end)}`
                    : formatPercent(segment.confidence) ?? ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
