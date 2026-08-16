import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

export default function HeroSection() {
  return (
    <section className="relative overflow-hidden border-b border-line bg-parchment transition-colors duration-300">
      {/* Signature motif: a single temple-arch line drawing, echoing the
          kalasha silhouette of a Bharatanatyam stage backdrop — quiet,
          used once, never repeated as decoration elsewhere on the page. */}
      <svg
        className="pointer-events-none absolute -right-40 -top-24 h-[560px] w-[560px] text-vermilion-500/[0.06] sm:-right-20"
        viewBox="0 0 400 400"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M200 20c70 55 110 125 110 195a110 110 0 0 1-220 0c0-70 40-140 110-195Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M200 70c50 42 80 96 80 150a80 80 0 0 1-160 0c0-54 30-108 80-150Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <circle cx="200" cy="255" r="26" stroke="currentColor" strokeWidth="1.5" />
      </svg>

      <div className="relative mx-auto grid max-w-7xl gap-14 px-6 py-24 sm:py-28 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:px-10 lg:py-32">
        <div className="animate-fadeUp">
          <p className="eyebrow mb-6">Mudra · Bhava · Pose · Audio · Evidence · Story</p>
          <h1 className="text-5xl leading-[1.05] text-espresso sm:text-6xl lg:text-7xl">
            HI-Natya <span className="italic text-vermilion-500">Verse</span>
          </h1>
          <p className="mt-6 font-display text-2xl italic text-espresso-light sm:text-3xl">
            "Where Dance Becomes Story"
          </p>
          <p className="mt-6 max-w-lg text-base leading-relaxed text-espresso-light">
            Understand Bharatanatyam performances through multimodal artificial intelligence —
            grounded in evidence, expressed as story.
          </p>

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link to="/analyze" className="btn-primary">
              Analyze a Performance
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <a href="#how-it-works" className="btn-secondary">
              Explore How It Works
            </a>
          </div>
        </div>

        <div className="relative animate-fadeIn [animation-delay:150ms]">
          <div className="card-surface relative mx-auto aspect-[4/5] w-full max-w-sm overflow-hidden p-0">
            {/* Placeholder composition standing in for a Bharatanatyam performance
                still — swap the <div> below for an <img src="/assets/hero-performance.jpg" />
                once a production photograph is available. */}
            <div className="flex h-full w-full flex-col items-center justify-center gap-6 bg-gradient-to-b from-parchment-100 to-parchment-200 px-8 text-center">
              <svg viewBox="0 0 120 160" className="h-40 w-32 text-vermilion-500/70" aria-hidden="true">
                <path
                  d="M60 8c-18 20-28 20-34 44-5 20 4 40 20 50-10 4-20 14-22 30h72c-2-16-12-26-22-30 16-10 25-30 20-50-6-24-16-24-34-44Z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path d="M28 100c-14 6-20 18-20 30M92 100c14 6 20 18 20 30" stroke="currentColor" strokeWidth="2" />
              </svg>
              <p className="text-xs uppercase tracking-widest2 text-espresso-faint">Bharatanatyam · AI interpretation</p>
            </div>
          </div>
          <div className="absolute -bottom-6 -left-6 hidden rounded-card border border-line bg-card px-5 py-4 shadow-lift sm:block">
            <p className="eyebrow mb-1">Evidence-grounded</p>
            <p className="text-sm text-espresso-light">Unresolved meanings stay unresolved.</p>
          </div>
        </div>
      </div>
    </section>
  )
}
