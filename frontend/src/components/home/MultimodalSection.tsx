import { Hand, Smile, PersonStanding, AudioLines, Layers } from 'lucide-react'
import SectionHeading from '@/components/common/SectionHeading'
import FeatureCard from '@/components/home/FeatureCard'

const FEATURES = [
  { icon: Hand, title: 'Mudra', description: 'Hand gesture recognition and knowledge-base grounding.' },
  { icon: Smile, title: 'Bhava', description: 'Facial expression and emotional-state analysis.' },
  { icon: PersonStanding, title: 'Pose', description: 'Body movement and performance-pose analysis.' },
  { icon: AudioLines, title: 'Audio', description: 'Audio and lyric/context analysis.' },
]

export default function MultimodalSection() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-7xl px-6 py-24 lg:px-10">
        <SectionHeading
          eyebrow="Multimodal AI"
          title="Four evidence streams, one interpretation"
          description="Every performance is read through four independent lenses before any story is written."
        />

        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature) => (
            <FeatureCard key={feature.title} {...feature} />
          ))}
        </div>

        <div className="mt-8 flex items-start gap-5 rounded-card border border-gold-300/50 bg-gold-50/60 p-7">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-gold-500/40 text-gold-600">
            <Layers className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-lg text-espresso">Multimodal Interpretation</h3>
            <p className="mt-2 text-sm leading-relaxed text-espresso-light">
              Combining visual, emotional and audio evidence to construct a grounded interpretation.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
