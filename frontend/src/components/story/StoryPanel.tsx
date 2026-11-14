import type { NarrativeGenerationResponse } from '@/types/analysis'

interface StoryPanelProps {
  story: NarrativeGenerationResponse
  demonstration?: boolean
  evidenceUsed?: Array<{ event_id: string; statement: string; type: string }>
}

export default function StoryPanel({ story, demonstration = false, evidenceUsed = [] }: StoryPanelProps) {
  const isGenerated = story.status === 'generated' && story.narrative
  const heading = isGenerated
    ? (story.mode === 'evidence_based' ? 'Story' : story.mode === 'pure_dance' ? 'Performance Interpretation' : 'Dance Story')
    : 'Story unavailable for this performance'

  return (
    <article className="card-surface p-7 sm:p-10 lg:p-14">
      {demonstration && <p className="mb-3 inline-block bg-gold-100 px-2 py-1 text-xs font-medium text-espresso">DEMONSTRATION PERFORMANCE</p>}
      <p className="eyebrow">{isGenerated ? heading : 'Evidence limitation'}</p>
      <h1 className="mt-4 font-display text-3xl leading-tight text-espresso sm:text-5xl">{story.title ?? heading}</h1>
      <div className="mt-8 rule-gold" />
      {isGenerated ? (
        <section className="mt-8"><p className="whitespace-pre-line text-base leading-loose text-espresso-light">{story.narrative}</p></section>
      ) : (
        <section className="mt-8 rounded-sm border border-unresolved/30 bg-unresolved-bg p-6">
          <h2 className="text-sm font-medium uppercase tracking-wide text-unresolved">{story.mode === 'evidence_based' ? 'Evidence-based interpretation unavailable' : 'No verified narrative available'}</h2>
          <p className="mt-3 text-sm leading-relaxed text-espresso-light">{story.message ?? 'Generation is unavailable because the required verified evidence is unavailable.'}</p>
        </section>
      )}
      {story.used_event_ids.length > 0 && (
        <details className="mt-10 rounded-sm border border-line bg-parchment/60 p-5">
          <summary className="cursor-pointer text-sm font-medium text-espresso">
            Evidence References ({story.used_event_ids.length})
          </summary>
          <p className="mt-2 text-sm text-espresso-faint">Chronological identifiers for the evidence reviewed by the validated backend response.</p>
          <ul className="mt-4 flex flex-wrap gap-2">{story.used_event_ids.map((eventId) => <li key={eventId} className="rounded border border-line px-2 py-1 font-mono text-xs text-espresso-light">{eventId}</li>)}</ul>
        </details>
      )}
      {demonstration && <details className="mt-10 rounded-sm border border-line bg-parchment/60 p-6"><summary className="cursor-pointer text-sm font-medium text-espresso">Evidence used for this story</summary><p className="mt-2 text-xs text-espresso-faint">Verified narrative evidence only. Model observations and technical artifacts are not story inputs.</p><ul className="mt-4 space-y-3">{evidenceUsed.map((event) => <li key={event.event_id} className="text-sm text-espresso-light">{event.statement}</li>)}</ul></details>}
    </article>
  )
}
