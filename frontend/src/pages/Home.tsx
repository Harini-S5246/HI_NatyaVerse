import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import HeroSection from '@/components/home/HeroSection'
import HowItWorks from '@/components/home/HowItWorks'
import MultimodalSection from '@/components/home/MultimodalSection'
import SectionHeading from '@/components/common/SectionHeading'

export default function Home() {
  return (
    <>
      <HeroSection />
      <HowItWorks />
      <MultimodalSection />

      <section className="mx-auto max-w-7xl px-6 py-24 lg:px-10">
        <SectionHeading
          eyebrow="Data-grounded design"
          title="Detected, grounded, interpreted, uncertain"
          description="HI-Natya Verse always distinguishes what the models detected from what the knowledge base could confirm — and never rewrites an unresolved result as certain."
        />

        <div className="mt-12 flex flex-col items-stretch gap-0 overflow-hidden rounded-card border border-line bg-card sm:flex-row">
          {[
            { label: 'Detected', description: 'Raw output from the mudra, bhava, pose and audio models.' },
            { label: 'Grounded', description: 'Confirmed against the Bharatanatyam knowledge base.' },
            { label: 'Interpreted', description: 'Reasoned from the combined multimodal evidence.' },
            { label: 'Uncertain', description: 'Left unresolved rather than guessed at.' },
          ].map((item, index, arr) => (
            <div
              key={item.label}
              className={`flex-1 p-7 ${index < arr.length - 1 ? 'border-b border-line sm:border-b-0 sm:border-r' : ''}`}
            >
              <p className="eyebrow">{item.label}</p>
              <p className="mt-2 text-sm leading-relaxed text-espresso-light">{item.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-line bg-espresso">
        <div className="mx-auto max-w-4xl px-6 py-24 text-center lg:px-10">
          <p className="eyebrow mb-5 text-gold-300">Begin</p>
          <h2 className="text-3xl leading-tight text-parchment-50 sm:text-4xl">
            An intelligent space where performance is observed, understood, and transformed into story.
          </h2>
          <Link
            to="/analyze"
            className="btn-primary mt-10 bg-vermilion-500 hover:bg-vermilion-400"
          >
            Analyze a Performance
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  )
}
