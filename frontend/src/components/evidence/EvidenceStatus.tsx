import { BookCheck, BrainCircuit, Database, Headphones } from 'lucide-react'
import type { CanonicalAnalysis } from '@/types/analysis'
import {
  hasBhavaModelObservation,
  hasMudraModelObservation,
  hasProductionVerifiedNarrativeEvidence,
  hasTechnicalAudioEvidence,
} from '@/utils/evidenceStatus'

interface EvidenceStatusProps { analysis: CanonicalAnalysis }

export default function EvidenceStatus({ analysis }: EvidenceStatusProps) {
  const { fusion, audioEvidence, performanceInterpretation, narrativeEvidenceReview } = analysis
  const mudraAvailable = hasMudraModelObservation(analysis.mudra)
  const bhavaAvailable = hasBhavaModelObservation(analysis.bhava)
  const hasModelObservations = mudraAvailable || bhavaAvailable
  const technicalAudioAvailable = hasTechnicalAudioEvidence(audioEvidence)
  const knowledgeReferenceCount = fusion.evidence.grounded.length
  const verifiedEligible = hasProductionVerifiedNarrativeEvidence(performanceInterpretation)
  const reviewRecords = narrativeEvidenceReview?.records ?? []
  const reviewSummary = reviewRecords.length
    ? `${reviewRecords.filter((record) => record.status === 'submitted').length} submitted, ${reviewRecords.filter((record) => record.status === 'verified').length} verified, ${reviewRecords.filter((record) => record.status === 'rejected').length} rejected.`
    : 'No curator review records are available.'
  const storyMessage = 'No production-verified narrative evidence is currently available for this performance. The system does not generate unsupported story content.'

  const items = [
    { title: 'Model observations', available: hasModelObservations, Icon: BrainCircuit, detail: `Mudra: ${mudraAvailable ? 'available' : 'unavailable'}. Facial-expression model: ${bhavaAvailable ? 'available' : 'unavailable'}.`, limitation: 'Classification outputs produced by trained models. Facial-expression labels are not classical Bhava or Rasa classifications. These do not independently verify performer intent or narrative meaning.' },
    { title: 'Technical evidence', available: technicalAudioAvailable, Icon: Headphones, detail: technicalAudioAvailable ? 'Audio metadata and extraction are available. Status: technical_only.' : audioEvidence?.availability.reason ?? 'No usable technical audio artifact is available.', limitation: 'Technical metadata and processing evidence. Not used as narrative evidence.' },
    { title: 'Mudra knowledge-base references', available: knowledgeReferenceCount > 0, Icon: Database, detail: knowledgeReferenceCount > 0 ? `${knowledgeReferenceCount} recognized-label reference entr${knowledgeReferenceCount === 1 ? 'y is' : 'ies are'} available.` : 'No recognized-label reference information is available.', limitation: 'Verification status varies by claim. Reference information associated with recognized labels does not establish that the same meaning or intent was expressed in the uploaded performance.' },
    { title: 'Verified narrative evidence', available: verifiedEligible, Icon: BookCheck, detail: verifiedEligible ? `${performanceInterpretation?.events.length ?? 0} production-eligible verified event${performanceInterpretation?.events.length === 1 ? '' : 's'} are available.` : storyMessage, limitation: verifiedEligible ? 'Only source-backed evidence explicitly reviewed and marked production eligible can reach Story generation.' : `${reviewSummary} Story generation is not eligible.` },
  ]

  return <section className="mt-16" aria-labelledby="evidence-status-heading">
    <p className="eyebrow">Evidence classification</p>
    <h2 id="evidence-status-heading" className="mt-2 font-display text-3xl text-espresso">Evidence status</h2>
    <div className="mt-6 grid gap-4 sm:grid-cols-2">
      {items.map(({ title, available, Icon, detail, limitation }) => <article className="border border-line bg-card-surface p-5" key={title}>
        <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-espresso"><Icon className="h-4 w-4" aria-hidden="true" /><h3 className="text-sm font-medium">{title}</h3></div><span className={`px-2 py-1 text-xs font-medium ${available ? 'bg-emerald-100 text-emerald-900' : 'bg-stone-100 text-stone-700'}`}>{available ? 'Available' : 'Unavailable'}</span></div>
        <p className="mt-4 text-sm leading-relaxed text-espresso-light">{detail}</p>
        <p className="mt-3 text-xs leading-relaxed text-espresso-faint">{limitation}</p>
      </article>)}
    </div>
    {fusion.evidence.unresolved.length > 0 && <p className="mt-4 border-l-2 border-amber-400 pl-3 text-sm text-espresso-light">Unresolved observations: {fusion.evidence.unresolved.length}. They are not automatically promoted into narrative claims.</p>}
  </section>
}
