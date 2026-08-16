import type { StoryInterpretation, StoryResponse } from '@/types/analysis'

interface StoryPanelProps {
  story: StoryInterpretation | StoryResponse
}

export default function StoryPanel({ story }: StoryPanelProps) {
  // Handle new StoryResponse format
  const isNewFormat = 'status' in story && 'interpretations' in story
  
  if (isNewFormat) {
    const response = story as StoryResponse
    return (
      <article className="card-surface p-10 sm:p-14">
        <p className="eyebrow">
          {response.status === 'completed' ? 'Evidence-Grounded Interpretation' : 'Interpretation'}
        </p>
        <h1 className="mt-4 font-display text-4xl leading-tight text-espresso sm:text-5xl">
          {response.title ?? 'Untitled interpretation'}
        </h1>

        <div className="mt-10 rule-gold" />

        {response.status === 'insufficient_grounded_evidence' && response.message && (
          <section className="mt-10 rounded-sm border border-unresolved/30 bg-unresolved-bg p-6">
            <h2 className="text-sm font-medium uppercase tracking-wide text-unresolved">No Grounded Evidence</h2>
            <p className="mt-3 text-sm leading-relaxed text-espresso-light">{response.message}</p>
          </section>
        )}

        {response.status === 'completed' && response.story && (
          <section className="mt-10">
            <p className="whitespace-pre-line text-base leading-loose text-espresso-light">{response.story}</p>
          </section>
        )}

        {response.interpretations && response.interpretations.length > 0 && (
          <section className="mt-10">
            <h2 className="text-lg text-espresso">Interpretations</h2>
            <ul className="mt-4 space-y-4">
              {response.interpretations.map((interp) => (
                <li key={interp.id} className="border-l-2 border-gold-500 pl-4 text-sm text-espresso-light">
                  <p className="font-display text-base text-espresso">{interp.id}</p>
                  <p className="mt-2">{interp.statement}</p>
                  {interp.confidence !== null && interp.confidence !== undefined && (
                    <p className="mt-1 text-xs text-espresso-faint">Confidence: {(interp.confidence * 100).toFixed(0)}%</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {response.unresolved_evidence && response.unresolved_evidence.length > 0 && (
          <section className="mt-10 rounded-sm border border-unresolved/30 bg-unresolved-bg p-6">
            <h2 className="text-sm font-medium uppercase tracking-wide text-unresolved">Unresolved Evidence</h2>
            <p className="mt-2 text-sm text-espresso-light">
              The following gestures were detected but lack verified knowledge-base entries:
            </p>
            <ul className="mt-3 space-y-1">
              {response.unresolved_evidence.map((item) => (
                <li key={item} className="text-sm text-espresso-light">
                  • {item}
                </li>
              ))}
            </ul>
          </section>
        )}
      </article>
    )
  }

  // Legacy StoryInterpretation format
  const legacy = story as StoryInterpretation
  return (
    <article className="card-surface p-10 sm:p-14">
      <p className="eyebrow">Interpretation</p>
      <h1 className="mt-4 font-display text-4xl leading-tight text-espresso sm:text-5xl">
        {legacy.title ?? 'Untitled interpretation'}
      </h1>

      {legacy.summary && (
        <p className="mt-6 font-display text-xl italic leading-relaxed text-espresso-light">{legacy.summary}</p>
      )}

      <div className="mt-10 rule-gold" />

      {legacy.narrative && (
        <section className="mt-10">
          <h2 className="text-lg text-espresso">Narrative Interpretation</h2>
          <p className="mt-3 whitespace-pre-line text-base leading-loose text-espresso-light">{legacy.narrative}</p>
        </section>
      )}

      {legacy.emotional_interpretation && (
        <section className="mt-10">
          <h2 className="text-lg text-espresso">Emotional Interpretation</h2>
          <p className="mt-3 whitespace-pre-line text-base leading-loose text-espresso-light">
            {legacy.emotional_interpretation}
          </p>
        </section>
      )}

      {legacy.grounded_gesture_interpretation && (
        <section className="mt-10">
          <h2 className="text-lg text-espresso">Grounded Gesture Interpretation</h2>
          <p className="mt-3 whitespace-pre-line text-base leading-loose text-espresso-light">
            {legacy.grounded_gesture_interpretation}
          </p>
        </section>
      )}

      {legacy.evidence_based_observations && legacy.evidence_based_observations.length > 0 && (
        <section className="mt-10">
          <h2 className="text-lg text-espresso">Evidence-based Observations</h2>
          <ul className="mt-3 space-y-2">
            {legacy.evidence_based_observations.map((observation, index) => (
              <li key={index} className="flex gap-3 text-base leading-relaxed text-espresso-light">
                <span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-gold-500" />
                {observation}
              </li>
            ))}
          </ul>
        </section>
      )}

      {legacy.uncertainties && legacy.uncertainties.length > 0 && (
        <section className="mt-10 rounded-sm border border-unresolved/30 bg-unresolved-bg p-6">
          <h2 className="text-sm font-medium uppercase tracking-wide text-unresolved">Uncertainties</h2>
          <ul className="mt-3 space-y-2">
            {legacy.uncertainties.map((item, index) => (
              <li key={index} className="text-sm leading-relaxed text-espresso-light">
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}

      {legacy.limitations && (
        <section className="mt-6">
          <h2 className="text-sm font-medium uppercase tracking-wide text-espresso-faint">Limitations</h2>
          <p className="mt-2 text-sm leading-relaxed text-espresso-faint">{legacy.limitations}</p>
        </section>
      )}
    </article>
  )
}
