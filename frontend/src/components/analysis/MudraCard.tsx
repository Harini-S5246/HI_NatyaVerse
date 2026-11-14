import type { MudraDetection } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface MudraCardProps {
  mudra: MudraDetection
}

export default function MudraCard({ mudra }: MudraCardProps) {
  const verifiedClaim =
    ['verified', 'partially_verified'].includes(mudra.verification_status ?? '') &&
    mudra.knowledge_status === mudra.verification_status &&
    Boolean(mudra.claim_id) &&
    Boolean(mudra.source_references?.length) &&
    Boolean(mudra.source_references?.every((reference) => reference.trim().length > 0))
  return (
    <div className="card-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <h4 className="font-display text-xl text-espresso">{mudra.name}</h4>
        {verifiedClaim ? (
          <span className="text-xs text-espresso-faint">{mudra.verification_status?.replaceAll('_', ' ')}</span>
        ) : <GroundingBadge status="unresolved" size="sm" />}
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-xs uppercase tracking-wide text-espresso-faint">Meaning</p>
        {verifiedClaim ? (
          <p className="text-sm text-espresso">{mudra.meaning ?? '—'}</p>
        ) : (
          <p className="text-sm italic text-espresso-faint">Meaning withheld or unavailable</p>
        )}
        {verifiedClaim && mudra.claim_id && <p className="text-xs text-espresso-faint">Claim: {mudra.claim_id}</p>}
        {verifiedClaim && mudra.source_references?.map((reference) => <p key={reference} className="text-xs text-espresso-faint">Source: {reference}</p>)}
        {verifiedClaim && mudra.uncertainty_notes?.map((note) => <p key={note} className="text-xs text-espresso-faint">Uncertainty: {note}</p>)}
        {!verifiedClaim && mudra.uncertainty_reason && <p className="text-xs text-espresso-faint">{mudra.uncertainty_reason}</p>}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-4 text-xs text-espresso-faint">
        <span>{formatPercent(mudra.confidence) ?? 'Confidence pending'}</span>
        {mudra.occurrence_count !== undefined && <span>{mudra.occurrence_count}× detected</span>}
      </div>
    </div>
  )
}
