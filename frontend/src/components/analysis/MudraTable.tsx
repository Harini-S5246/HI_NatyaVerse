import type { MudraDetection } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface MudraTableProps {
  mudras: MudraDetection[]
}

export default function MudraTable({ mudras }: MudraTableProps) {
  if (mudras.length === 0) {
    return <p className="text-sm text-espresso-faint">No mudras were reported by the backend for this performance.</p>
  }

  return (
    <div className="card-surface overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-espresso-faint">
            <th className="px-6 py-4 font-medium">Mudra</th>
            <th className="px-6 py-4 font-medium">Status</th>
            <th className="px-6 py-4 font-medium">Meaning</th>
            <th className="px-6 py-4 font-medium">Confidence</th>
            <th className="px-6 py-4 font-medium">Occurrences</th>
          </tr>
        </thead>
        <tbody>
          {mudras.map((mudra, index) => {
            const verifiedClaim =
              ['verified', 'partially_verified'].includes(mudra.verification_status ?? '') &&
              mudra.knowledge_status === mudra.verification_status &&
              Boolean(mudra.claim_id) &&
              Boolean(mudra.source_references?.length) &&
              Boolean(mudra.source_references?.every((reference) => reference.trim().length > 0))
            return (
            <tr key={`${mudra.name}-${mudra.segment_start ?? index}`} className="border-b border-line last:border-0">
              <td className="px-6 py-4 font-display text-base text-espresso">{mudra.name}</td>
              <td className="px-6 py-4">
                {verifiedClaim ? (
                  <span className="text-xs text-espresso-faint">{mudra.verification_status?.replaceAll('_', ' ')}</span>
                ) : <GroundingBadge status="unresolved" size="sm" />}
              </td>
              <td className="px-6 py-4 text-espresso-light">
                {verifiedClaim ? (mudra.meaning ?? '—') : <span className="italic text-espresso-faint">Meaning withheld or unavailable</span>}
                {verifiedClaim && mudra.claim_id && <p className="mt-1 text-xs text-espresso-faint">Claim: {mudra.claim_id}</p>}
                {verifiedClaim && mudra.source_references?.map((reference) => <p key={reference} className="mt-1 text-xs text-espresso-faint">Source: {reference}</p>)}
                {verifiedClaim && mudra.uncertainty_notes?.map((note) => <p key={note} className="mt-1 text-xs text-espresso-faint">Uncertainty: {note}</p>)}
                {!verifiedClaim && mudra.uncertainty_reason && <p className="mt-1 text-xs text-espresso-faint">{mudra.uncertainty_reason}</p>}
              </td>
              <td className="px-6 py-4 text-espresso-light">{formatPercent(mudra.confidence) ?? '—'}</td>
              <td className="px-6 py-4 text-espresso-light">{mudra.occurrence_count ?? '—'}</td>
            </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
