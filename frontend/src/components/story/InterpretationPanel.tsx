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
        <p className="eyebrow">Evidence supporting this story</p>

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
              <span className="text-xs font-medium text-espresso-faint">Knowledge-base references</span>
              <span className="text-xs text-espresso-faint">{evidence.grounded.length}</span>
            </div>
            <ul className="space-y-1.5">
              {evidence.grounded.map((item) => (
                <li key={item.id} className="text-sm text-espresso-light">
                  <span className="font-medium text-espresso">{item.label}</span>
                  {['verified', 'partially_verified'].includes(item.verification_status ?? '') &&
                  item.knowledge_status === item.verification_status &&
                  item.claim_id &&
                  item.source_references?.length &&
                  item.source_references.every((reference) => reference.trim().length > 0) ? (
                    <>
                      {item.detail && <span> → {item.detail}</span>}
                      <p className="text-xs text-espresso-faint">
                        {item.verification_status?.replaceAll('_', ' ')} · Claim: {item.claim_id}
                      </p>
                      {item.source_references.map((reference) => (
                        <p key={`${item.id}-${reference}`} className="text-xs text-espresso-faint">Source: {reference}</p>
                      ))}
                      {item.uncertainty_notes?.map((note) => (
                        <p key={`${item.id}-${note}`} className="text-xs text-espresso-faint">Uncertainty: {note}</p>
                      ))}
                    </>
                  ) : (
                    <p className="text-xs text-espresso-faint">Meaning withheld: verification provenance unavailable.</p>
                  )}
                  {item.uncertainty_reason && (
                    <p className="text-xs text-espresso-faint">{item.uncertainty_reason}</p>
                  )}
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
