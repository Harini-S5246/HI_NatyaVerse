import { CheckCircle2, AlertTriangle } from 'lucide-react'
import type { Evidence } from '@/types/analysis'

interface WhyInterpretationProps {
  evidence: Evidence
}

/**
 * Builds its list entirely from the evidence the backend actually returned
 * (grounded + detected + interpreted read as affirmative signals, unresolved
 * read as caveats). Nothing here is hardcoded copy standing in for real data.
 */
export default function WhyInterpretation({ evidence }: WhyInterpretationProps) {
  const affirmative = [...evidence.grounded, ...evidence.detected, ...evidence.interpreted]
  const caveats = evidence.unresolved

  if (affirmative.length === 0 && caveats.length === 0) {
    return null
  }

  return (
    <div className="card-surface p-8">
      <h3 className="font-display text-2xl text-espresso">Why this interpretation?</h3>

      <ul className="mt-6 space-y-3">
        {affirmative.map((item) => (
          <li key={item.id} className="flex items-start gap-3 text-sm text-espresso">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-grounded" aria-hidden="true" />
            <span>{item.label}</span>
          </li>
        ))}
        {caveats.map((item) => (
          <li key={item.id} className="flex items-start gap-3 text-sm text-espresso-light">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-unresolved" aria-hidden="true" />
            <span>
              {item.label}
              {item.detail && <span className="text-espresso-faint"> — {item.detail}</span>}
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-6 border-t border-line pt-5 text-xs leading-relaxed text-espresso-faint">
        The interpretation is generated from the available multimodal evidence. Unresolved gesture
        meanings and unsupported narrative claims are intentionally excluded.
      </p>
    </div>
  )
}
