import { CheckCircle2, AlertTriangle, ScanEye, Sparkles } from 'lucide-react'
import type { GroundingStatus } from '@/types/analysis'

interface GroundingBadgeProps {
  status: GroundingStatus
  size?: 'sm' | 'md'
}

const CONFIG: Record<
  GroundingStatus,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  grounded: {
    label: 'Grounded',
    icon: CheckCircle2,
    className: 'bg-grounded-bg text-grounded border-grounded/30',
  },
  unresolved: {
    label: 'Unresolved',
    icon: AlertTriangle,
    className: 'bg-unresolved-bg text-unresolved border-unresolved/30',
  },
  detected: {
    label: 'Detected',
    icon: ScanEye,
    className: 'bg-gold-50 text-gold-600 border-gold-300/60',
  },
  interpreted: {
    label: 'Interpreted',
    icon: Sparkles,
    className: 'bg-vermilion-50 text-vermilion-600 border-vermilion-100',
  },
}

export default function GroundingBadge({ status, size = 'md' }: GroundingBadgeProps) {
  const config = CONFIG[status]
  const Icon = config.icon

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.className} ${
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-3 py-1 text-xs'
      }`}
    >
      <Icon className={size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'} aria-hidden="true" />
      {config.label}
    </span>
  )
}
