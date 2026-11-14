import { ArrowRight, BookOpen, BrainCircuit, Database, FileVideo, GitMerge, Headphones, PackageCheck, ScanLine, UserCheck } from 'lucide-react'
import type { CanonicalAnalysis } from '@/types/analysis'
import { hasBhavaModelObservation, hasMudraModelObservation, hasProductionVerifiedNarrativeEvidence, hasTechnicalAudioEvidence } from '@/utils/evidenceStatus'

type TimelineStep = { title: string; category: string; available: boolean; note: string; Icon: typeof FileVideo }

export default function EvidenceProvenanceTimeline({ analysis }: { analysis: CanonicalAnalysis }) {
  const modelAvailable = hasMudraModelObservation(analysis.mudra) || hasBhavaModelObservation(analysis.bhava)
  const storyEligible = hasProductionVerifiedNarrativeEvidence(analysis.performanceInterpretation)
  const steps: TimelineStep[] = [
    { title: 'Uploaded Video', category: 'Source artifact', available: true, note: 'Persisted upload source', Icon: FileVideo },
    { title: 'Frame Sampling', category: 'Processing evidence', available: modelAvailable, note: modelAvailable ? 'Sampled frames support model inputs' : 'No sampled-frame model output', Icon: ScanLine },
    { title: 'Mudra Model', category: 'Model Observation', available: hasMudraModelObservation(analysis.mudra), note: `${analysis.mudra.prediction_count} persisted predictions`, Icon: BrainCircuit },
    { title: 'Facial-expression Model', category: 'Model Observation', available: hasBhavaModelObservation(analysis.bhava), note: `${analysis.bhava.prediction_count} generic predicted emotion labels`, Icon: BrainCircuit },
    { title: 'Fusion', category: 'Processing evidence', available: analysis.fusion.status === 'completed', note: 'Timestamp alignment only; no narrative inference', Icon: GitMerge },
    { title: 'Technical Audio', category: 'Technical Evidence', available: hasTechnicalAudioEvidence(analysis.audioEvidence), note: hasTechnicalAudioEvidence(analysis.audioEvidence) ? 'technical_only' : 'Unavailable', Icon: Headphones },
    { title: 'Mudra knowledge-base references', category: 'Knowledge Grounding', available: analysis.fusion.evidence.grounded.length > 0, note: `${analysis.fusion.evidence.grounded.length} persisted references; verification status varies by claim`, Icon: Database },
    { title: 'Human Verification', category: 'Human-Verified Evidence', available: storyEligible, note: storyEligible ? 'Production-eligible verification available' : 'Human verification required', Icon: UserCheck },
    { title: 'Performance Interpretation Package', category: 'Human-Verified Evidence', available: storyEligible, note: storyEligible ? 'Available and production eligible' : 'Unavailable', Icon: PackageCheck },
    { title: 'Story Generation', category: 'LLM-Generated Content', available: storyEligible, note: storyEligible ? 'Eligible; not invoked on this page' : 'Unavailable due to insufficient verified evidence', Icon: BookOpen },
  ]

  return <section className="mt-16" aria-labelledby="evidence-flow-heading">
    <p className="eyebrow">Evidence provenance timeline</p>
    <h2 id="evidence-flow-heading" className="mt-2 font-display text-3xl text-espresso">How artifacts remain separate</h2>
    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-espresso-light">This flow traces artifact provenance, not a promotion path. Model observations, technical evidence, and knowledge grounding do not automatically become human-verified narrative evidence.</p>
    <ol className="mt-6 flex gap-3 overflow-x-auto pb-3">
      {steps.map((step, index) => <li key={step.title} className="flex shrink-0 items-stretch gap-3">
        <article className="w-52 border border-line bg-card-surface p-4">
          <div className="flex items-center justify-between gap-2"><step.Icon className="h-4 w-4 text-espresso" aria-hidden="true" /><span className={`px-2 py-1 text-xs font-medium ${step.available ? 'bg-emerald-100 text-emerald-900' : 'bg-stone-100 text-stone-700'}`}>{step.available ? 'Available' : 'Unavailable'}</span></div>
          <h3 className="mt-4 text-sm font-medium text-espresso">{step.title}</h3>
          <p className="mt-2 text-xs font-medium text-espresso-light">{step.category}</p>
          <p className="mt-2 text-xs leading-relaxed text-espresso-faint">{step.note}</p>
        </article>
        {index < steps.length - 1 && <ArrowRight className="my-auto h-4 w-4 shrink-0 text-espresso-faint" aria-hidden="true" />}
      </li>)}
    </ol>
  </section>
}
