import { Check, Loader2 } from 'lucide-react'
import type { AnalysisStatus } from '@/types/analysis'

interface ProcessingStagesProps {
  status: AnalysisStatus | null
}

/**
 * The backend may only expose a single coarse status field ("processing" /
 * "completed" / "failed") or it may expose a granular `stage` string. This
 * component adapts to either: when a specific stage is known it is shown as
 * the active step; when it is not, a single honest "AI analysis in
 * progress" indicator is shown instead of fabricating stage completion.
 */
const KNOWN_STAGES = [
  { key: 'video_prepared', label: 'Video prepared' },
  { key: 'movement_detected', label: 'Movement detected' },
  { key: 'mudra', label: 'Mudras analyzed' },
  { key: 'bhava', label: 'Bhava analyzed' },
  { key: 'pose', label: 'Pose analyzed' },
  { key: 'audio', label: 'Audio analysis' },
  { key: 'multimodal_reasoning', label: 'Multimodal reasoning' },
  { key: 'story_generation', label: 'Story generation' },
  { key: 'finalizing', label: 'Finalizing interpretation' },
]

export default function ProcessingStages({ status }: ProcessingStagesProps) {
  const knownStageKey = status?.stage
  const hasStageInfo = Boolean(knownStageKey)
  const activeIndex = hasStageInfo ? KNOWN_STAGES.findIndex((s) => s.key === knownStageKey) : -1

  return (
    <div className="card-surface p-8">
      {hasStageInfo ? (
        <ol className="space-y-4">
          {KNOWN_STAGES.map((stage, index) => {
            const isDone = activeIndex >= 0 && index < activeIndex
            const isActive = index === activeIndex

            return (
              <li key={stage.key} className="flex items-center gap-3">
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${
                    isDone
                      ? 'border-grounded bg-grounded text-parchment-50'
                      : isActive
                        ? 'border-vermilion-500 text-vermilion-500'
                        : 'border-line text-espresso-faint'
                  }`}
                >
                  {isDone ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : isActive ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  )}
                </span>
                <span className={`text-sm ${isDone || isActive ? 'text-espresso' : 'text-espresso-faint'}`}>
                  {stage.label}
                </span>
              </li>
            )
          })}
        </ol>
      ) : (
        <div className="flex items-center gap-4 py-6">
          <Loader2 className="h-6 w-6 shrink-0 animate-spin text-vermilion-500" aria-hidden="true" />
          <div>
            <p className="text-sm text-espresso">{status?.message ?? 'AI analysis in progress'}</p>
            <p className="mt-1 text-xs text-espresso-faint">
              Detailed stage-by-stage progress will appear here once the backend reports it.
            </p>
          </div>
        </div>
      )}

      {status?.progress !== undefined && (
        <div className="mt-8">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-parchment-200">
            <div
              className="h-full rounded-full bg-vermilion-500 transition-all duration-700 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, status.progress))}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
