import SectionHeading from '@/components/common/SectionHeading'

const STEPS = [
  {
    number: '01',
    title: 'Upload',
    description: 'Upload a Bharatanatyam performance.',
  },
  {
    number: '02',
    title: 'Multimodal Analysis',
    description: 'The system analyzes Mudra, Pose, Bhava and Audio.',
  },
  {
    number: '03',
    title: 'Evidence Grounding',
    description: 'The system separates grounded evidence, unresolved information and model confidence.',
  },
  {
    number: '04',
    title: 'Interpretation',
    description: 'The multimodal evidence is combined.',
  },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="border-b border-line bg-parchment-100/50">
      <div className="mx-auto max-w-7xl px-6 py-24 lg:px-10">
        <SectionHeading
          eyebrow="The process"
          title="From performance to story, in four grounded stages"
          description="Each stage of HI-Natya Verse builds on the evidence of the last — nothing in the final story skips the chain."
        />

        <ol className="mt-16 grid gap-x-8 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((step, index) => (
            <li
              key={step.number}
              className="animate-fadeUp [animation-fill-mode:both] transition-transform duration-300 hover:-translate-y-1"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <div className="flex items-baseline gap-4">
                <span className="font-display text-3xl text-gold-500">{step.number}</span>
                <div className="h-px flex-1 bg-line" />
              </div>
              <h3 className="mt-4 text-xl text-espresso">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-espresso-light">{step.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
