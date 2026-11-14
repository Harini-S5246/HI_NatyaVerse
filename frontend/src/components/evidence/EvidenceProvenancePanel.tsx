import { ChevronDown, Database, Headphones, ScanLine, Sparkles, UserCheck } from 'lucide-react'
import type { CanonicalAnalysis, NarrativeEvidenceReviewSummary } from '@/types/analysis'
import { formatPercent } from '@/utils/format'
import {
  hasBhavaModelObservation,
  hasMudraModelObservation,
  hasProductionVerifiedNarrativeEvidence,
  hasTechnicalAudioEvidence,
} from '@/utils/evidenceStatus'

type Detail = { label: string; value: string }

function DetailList({ details }: { details: Detail[] }) {
  return <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
    {details.map((detail) => <div key={detail.label}>
      <dt className="text-xs uppercase tracking-wide text-espresso-faint">{detail.label}</dt>
      <dd className="mt-1 break-words text-espresso-light">{detail.value}</dd>
    </div>)}
  </dl>
}

function narrativeDetails(review: NarrativeEvidenceReviewSummary | null, storyEligible: boolean): Detail[] {
  const records = review?.records ?? []
  const count = (status: 'draft' | 'submitted' | 'verified', eligible?: boolean) => records.filter((record) => record.status === status && (eligible === undefined || (record.production_eligibility.status === 'eligible') === eligible)).length
  const states = [
    `Unavailable: ${records.length === 0 ? 'no review records' : 'not applicable'}`,
    `Draft: ${count('draft')}`,
    `Submitted: ${count('submitted')}`,
    `Verified but ineligible: ${count('verified', false)}`,
    `Verified and production eligible: ${storyEligible ? 'yes — Story eligible' : `${count('verified', true)} — Performance Interpretation Package unavailable`}`,
  ]
  return [
    { label: 'Review states', value: states.join(' | ') },
    { label: 'Story eligibility', value: storyEligible ? 'Yes — an available production-eligible Performance Interpretation Package exists.' : 'No — Story generation is unavailable due to insufficient verified evidence.' },
  ]
}

export default function EvidenceProvenancePanel({ analysis }: { analysis: CanonicalAnalysis }) {
  const mudraAvailable = hasMudraModelObservation(analysis.mudra)
  const bhavaAvailable = hasBhavaModelObservation(analysis.bhava)
  const audioAvailable = hasTechnicalAudioEvidence(analysis.audioEvidence)
  const storyEligible = hasProductionVerifiedNarrativeEvidence(analysis.performanceInterpretation)
  const groundedCount = analysis.fusion.evidence.grounded.length
  const sections = [
    {
      title: 'Mudra provenance', Icon: ScanLine, available: mudraAvailable,
      details: [
        { label: 'Evidence type', value: 'Model Observation' },
        { label: 'Source', value: 'Persisted Mudra classification output' },
        { label: 'Basis', value: 'Sampled video frames' },
        { label: 'Prediction count', value: String(analysis.mudra.prediction_count) },
        { label: 'Average confidence', value: analysis.mudra.summary.average_confidence == null ? 'Not reported' : (formatPercent(analysis.mudra.summary.average_confidence) ?? 'Not reported') },
      ],
      limitation: 'Mudra predictions are model observations and do not independently verify narrative intent.',
    },
    {
      title: 'Facial-expression model provenance', Icon: Sparkles, available: bhavaAvailable,
      details: [
        { label: 'Evidence type', value: 'Model Observation' },
        { label: 'Source', value: 'Persisted generic facial-expression classifier output' },
        { label: 'Basis', value: 'Sampled video frames' },
        { label: 'Prediction count', value: String(analysis.bhava.prediction_count) },
        { label: 'Average confidence', value: analysis.bhava.summary.average_confidence == null ? 'Not reported' : (formatPercent(analysis.bhava.summary.average_confidence) ?? 'Not reported') },
      ],
      limitation: "Predicted emotion labels are generic facial-expression observations, not classical Bhava or Rasa classifications; they do not verify the performer's internal emotional state or narrative intent.",
    },
    {
      title: 'Audio provenance', Icon: Headphones, available: audioAvailable,
      details: [
        { label: 'Evidence type', value: 'Technical Evidence' },
        { label: 'Source', value: audioAvailable ? 'Extracted audio stream' : 'No extracted audio artifact' },
        { label: 'Status', value: audioAvailable ? 'Available — extracted artifact exists' : analysis.audioEvidence?.extraction.status ?? 'Unavailable' },
        { label: 'Narrative eligibility', value: 'No' },
        { label: 'Artifact reference', value: audioAvailable ? (analysis.audioEvidence?.extraction.audio_reference || 'Not reported') : 'Not available' },
      ],
      limitation: 'Technical audio evidence is not used to infer lyrics, meaning, characters, actions, or story content.',
    },
    {
      title: 'Pose provenance', Icon: ScanLine, available: false,
      details: [
        { label: 'Evidence type', value: 'Unavailable' },
        { label: 'Source', value: 'No persisted pose result is available in the production Analysis response.' },
        { label: 'Status', value: 'Unavailable' },
      ],
      limitation: 'No pose evidence is displayed or inferred.',
    },
    {
      title: 'Curated knowledge provenance', Icon: Database, available: groundedCount > 0,
      details: [
        { label: 'Evidence type', value: 'Knowledge-Base Grounding' },
        { label: 'Source', value: 'Persisted grounded references in Fusion output' },
        { label: 'Reference count', value: String(groundedCount) },
        { label: 'Purpose', value: 'Traditional reference information associated with recognized labels' },
      ],
      limitation: 'Knowledge grounding does not prove that the dancer intended the associated meaning in this performance.',
    },
    {
      title: 'Verified narrative provenance', Icon: UserCheck, available: storyEligible,
      details: narrativeDetails(analysis.narrativeEvidenceReview, storyEligible),
      limitation: storyEligible
        ? 'Only source-backed evidence explicitly reviewed and marked production eligible reaches Story generation.'
        : 'No production-verified narrative evidence is currently available for this performance. The system does not generate unsupported story content.',
    },
  ]

  return <section className="mt-16" aria-labelledby="evidence-provenance-heading">
    <p className="eyebrow">Evidence details</p>
    <h2 id="evidence-provenance-heading" className="mt-2 font-display text-3xl text-espresso">Provenance and limitations</h2>
    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-espresso-light">Each status below is read from persisted backend artifacts or explicit review metadata. These records remain separate; they are not automatically promoted into narrative evidence.</p>
    <div className="mt-6 space-y-3">
      {sections.map(({ title, Icon, available, details, limitation }) => <details key={title} className="border border-line bg-card-surface p-5">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-espresso">
          <span className="flex items-center gap-2"><Icon className="h-4 w-4" aria-hidden="true" />{title}</span>
          <span className="flex items-center gap-3"><span className={`px-2 py-1 text-xs font-medium ${available ? 'bg-emerald-100 text-emerald-900' : 'bg-stone-100 text-stone-700'}`}>{available ? 'Available' : 'Unavailable'}</span><ChevronDown className="h-4 w-4" aria-hidden="true" /></span>
        </summary>
        <DetailList details={details} />
        <p className="mt-4 border-l-2 border-gold-400 pl-3 text-xs leading-relaxed text-espresso-faint">Limitation: {limitation}</p>
      </details>)}
    </div>
  </section>
}
