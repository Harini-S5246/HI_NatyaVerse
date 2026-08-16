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
          {mudras.map((mudra) => (
            <tr key={mudra.name} className="border-b border-line last:border-0">
              <td className="px-6 py-4 font-display text-base text-espresso">{mudra.name}</td>
              <td className="px-6 py-4">
                <GroundingBadge status={mudra.grounded ? 'grounded' : 'unresolved'} size="sm" />
              </td>
              <td className="px-6 py-4 text-espresso-light">
                {mudra.grounded ? (mudra.meaning ?? '—') : <span className="italic text-espresso-faint">Unresolved</span>}
              </td>
              <td className="px-6 py-4 text-espresso-light">{formatPercent(mudra.confidence) ?? '—'}</td>
              <td className="px-6 py-4 text-espresso-light">{mudra.occurrence_count ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
