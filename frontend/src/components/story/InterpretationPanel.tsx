import type { AnalysisResult, Evidence } from '@/types/analysis'
import { formatPercent, normalizeLevel } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface InterpretationPanelProps {
  evidence: Evidence
  result?: AnalysisResult | null
}

export default function InterpretationPanel({ evidence, result }: InterpretationPanelProps) {
  return (
    <aside className="lg:sticky lg:top-24 lg:self-start">
      <div className="card-surface p-7">
        <p className="eyebrow">Evidence</p>

        {(result?.overall_evidence_strength !== undefined || result?.confidence?.score !== undefined) && (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-wide text-espresso-faint">Overall confidence</p>
            <p className="mt-1 font-display text-2xl text-espresso">
              {formatPercent(result?.overall_evidence_strength ?? result?.confidence?.score) ?? '—'}
            </p>
            {(result?.evidence_level || result?.confidence?.level) && (
              <p className="mt-0.5 text-xs text-espresso-faint">
                {normalizeLevel(result?.evidence_level ?? result?.confidence?.level)}
              </p>
            )}
          </div>
        )}

        {evidence.grounded.length > 0 && (
          <div className="mt-6 border-t border-line pt-5">
            <div className="mb-3 flex items-center justify-between">
              <GroundingBadge status="grounded" size="sm" />
              <span className="text-xs text-espresso-faint">{evidence.grounded.length}</span>
            </div>
            <ul className="space-y-1.5">
              {evidence.grounded.map((item) => (
                <li key={item.id} className="text-sm text-espresso-light">
                  {item.label}
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidence.unresolved.length > 0 && (
          <div className="mt-6 border-t border-line pt-5">
            <div className="mb-3 flex items-center justify-between">
              <GroundingBadge status="unresolved" size="sm" />
              <span className="text-xs text-espresso-faint">{evidence.unresolved.length}</span>
            </div>
            <ul className="space-y-1.5">
              {evidence.unresolved.map((item) => (
                <li key={item.id} className="text-sm text-espresso-light">
                  {item.label}
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidence.grounded.length === 0 && evidence.unresolved.length === 0 && (
          <p className="mt-4 text-sm text-espresso-faint">
            No evidence breakdown was reported by the backend for this analysis.
          </p>
        )}
      </div>
    </aside>
  )
}
