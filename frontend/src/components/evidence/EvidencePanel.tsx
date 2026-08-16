import type { Evidence, EvidenceItem, GroundingStatus } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface EvidencePanelProps {
  evidence: Evidence
}

const SECTIONS: { key: keyof Evidence; status: GroundingStatus; title: string; helper: string }[] = [
  { key: 'grounded', status: 'grounded', title: 'Grounded', helper: 'Supported by the knowledge base.' },
  { key: 'detected', status: 'detected', title: 'Detected', helper: 'Obtained from model analysis.' },
  { key: 'interpreted', status: 'interpreted', title: 'Interpretation', helper: 'Inferred from combined evidence.' },
  { key: 'unresolved', status: 'unresolved', title: 'Unresolved', helper: 'Insufficient knowledge or evidence.' },
]

function EvidenceRow({ item }: { item: EvidenceItem }) {
  return (
    <li className="flex items-start justify-between gap-4 border-b border-line py-3 last:border-0">
      <div>
        <p className="text-sm text-espresso">{item.label}</p>
        {item.detail && <p className="mt-0.5 text-xs text-espresso-faint">{item.detail}</p>}
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
              <GroundingBadge status={section.status} size="sm" />
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
