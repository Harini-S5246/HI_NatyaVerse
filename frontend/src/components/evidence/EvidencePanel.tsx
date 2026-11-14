import type { Evidence, EvidenceItem, GroundingStatus } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface EvidencePanelProps {
  evidence: Evidence
}

const SECTIONS: { key: keyof Evidence; status: GroundingStatus; title: string; helper: string }[] = [
  { key: 'grounded', status: 'grounded', title: 'Knowledge-base reference', helper: 'Reference information associated with a recognized label; verification status is shown per claim.' },
  { key: 'detected', status: 'detected', title: 'Model observation', helper: 'Produced by model analysis; not verified narrative evidence.' },
  { key: 'interpreted', status: 'interpreted', title: 'Interpretation', helper: 'Inferred from combined evidence.' },
  { key: 'unresolved', status: 'unresolved', title: 'Unresolved observation', helper: 'Not automatically promoted into a narrative claim.' },
]

function EvidenceRow({ item }: { item: EvidenceItem }) {
  const canShowMeaning = item.category !== 'grounded' || (
    ['verified', 'partially_verified'].includes(item.verification_status ?? '') &&
    item.knowledge_status === item.verification_status &&
    Boolean(item.claim_id) &&
    Boolean(item.source_references?.length) &&
    Boolean(item.source_references?.every((reference) => reference.trim().length > 0))
  )
  const label = item.label
    .replace(/\s+(?:bhava|facial expression)\s+detected$/i, '')
  const displayLabel = label === item.label ? item.label : `${label} facial-expression observation`
  return (
    <li className="flex items-start justify-between gap-4 border-b border-line py-3 last:border-0">
      <div>
        <p className="text-sm text-espresso">{displayLabel}</p>
        {item.detail && canShowMeaning ? (
          <p className="mt-0.5 text-xs text-espresso-faint">{item.detail}</p>
        ) : item.category === 'grounded' ? (
          <p className="mt-0.5 text-xs text-espresso-faint">Meaning withheld: verification provenance unavailable.</p>
        ) : null}
        {item.verification_status && (
          <p className="mt-1 text-xs text-espresso-faint">
            {item.verification_status.replaceAll('_', ' ')}
          </p>
        )}
        {item.claim_id && <p className="mt-1 text-xs text-espresso-faint">Claim: {item.claim_id}</p>}
        {canShowMeaning && item.source_references?.map((reference) => (
          <p key={`${item.id}-${reference}`} className="mt-1 text-xs text-espresso-faint">Source: {reference}</p>
        ))}
        {canShowMeaning && item.uncertainty_notes?.map((note) => (
          <p key={`${item.id}-${note}`} className="mt-1 text-xs text-espresso-faint">Uncertainty: {note}</p>
        ))}
        {item.uncertainty_reason && (
          <p className="mt-1 text-xs text-espresso-faint">{item.uncertainty_reason}</p>
        )}
      </div>
      {item.confidence !== undefined && (
        <span className="shrink-0 text-xs text-espresso-faint">{formatPercent(item.confidence)}</span>
      )}
    </li>
  )
}

export default function EvidencePanel({ evidence }: EvidencePanelProps) {
  const hasAny = SECTIONS.some((section) => evidence[section.key].length > 0)

  if (!hasAny) {
    return (
      <div className="card-surface p-6">
        <p className="text-sm text-espresso-faint">No evidence breakdown was reported by the backend yet.</p>
      </div>
    )
  }

  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {SECTIONS.map((section) => {
        const items = evidence[section.key]
        if (items.length === 0) return null

        return (
          <div key={section.key} className="card-surface p-6">
            <div className="flex items-center justify-between">
              {section.status === 'grounded' ? (
                <span className="text-xs font-medium text-espresso-faint">Knowledge-base references</span>
              ) : <GroundingBadge status={section.status} size="sm" />}
              <span className="text-xs text-espresso-faint">{items.length}</span>
            </div>
            <p className="mt-2 text-xs text-espresso-faint">{section.helper}</p>
            <ul className="mt-3">
              {items.map((item) => (
                <EvidenceRow key={item.id} item={item} />
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
