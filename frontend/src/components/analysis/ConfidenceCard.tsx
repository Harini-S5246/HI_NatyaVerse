import { formatPercent, normalizeLevel, toPercent, levelFromScore } from '@/utils/format'

interface ConfidenceCardProps {
  label: string
  score?: number | null
  level?: string | null
  helperText?: string
}

const LEVEL_COLOR: Record<string, string> = {
  High: 'bg-grounded',
  Moderate: 'bg-gold-500',
  Low: 'bg-danger',
}

export default function ConfidenceCard({ label, score, level, helperText }: ConfidenceCardProps) {
  const pct = toPercent(score ?? undefined)
  const resolvedLevel = normalizeLevel(level ?? levelFromScore(score) ?? undefined)
  const barColor = (resolvedLevel && LEVEL_COLOR[resolvedLevel]) || 'bg-gold-500'

  return (
    <div className="card-surface p-6">
      <div className="flex items-baseline justify-between gap-4">
        <p className="eyebrow">{label}</p>
        {resolvedLevel && (
          <span className="rounded-full border border-line px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-espresso-light">
            {resolvedLevel}
          </span>
        )}
      </div>

      <p className="mt-3 font-display text-4xl text-espresso">
        {formatPercent(score) ?? <span className="text-espresso-faint">Pending</span>}
      </p>

      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-parchment-200">
        {pct !== null && (
          <div
            className={`h-full rounded-full ${barColor} transition-all duration-700 ease-out`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>

      {helperText && <p className="mt-3 text-xs leading-relaxed text-espresso-faint">{helperText}</p>}
    </div>
  )
}
