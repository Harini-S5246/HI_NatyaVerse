import { PersonStanding } from 'lucide-react'
import type { PoseAnalysis } from '@/types/analysis'
import { formatDuration, formatPercent } from '@/utils/format'

interface PoseCardProps {
  pose?: PoseAnalysis
}

export default function PoseCard({ pose }: PoseCardProps) {
  if (!pose || (!pose.primary_pose && (!pose.segments || pose.segments.length === 0))) {
    return (
      <div className="card-surface p-6">
        <p className="eyebrow">Pose</p>
        <p className="mt-4 text-sm text-espresso-faint">Not available in current analysis pipeline.</p>
      </div>
    )
  }

  return (
    <div className="card-surface p-6">
      <div className="flex items-center justify-between">
        <p className="eyebrow">Pose</p>
        <PersonStanding className="h-4 w-4 text-vermilion-500" aria-hidden="true" />
      </div>

      {pose.primary_pose && (
        <>
          <p className="mt-3 font-display text-3xl text-espresso">{pose.primary_pose}</p>
          <p className="mt-3 text-sm text-espresso-light">
            {formatPercent(pose.confidence ?? pose.pose_confidence) ?? 'Confidence pending'}
          </p>
        </>
      )}

      {pose.segments && pose.segments.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-xs uppercase tracking-wide text-espresso-faint">Segments</p>
          <ul className="mt-2 space-y-2">
            {pose.segments.map((segment, index) => (
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
