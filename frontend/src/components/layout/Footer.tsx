export default function Footer() {
  return (
    <footer id="about" className="border-t border-line bg-parchment-50 transition-colors duration-300">
      <div className="mx-auto max-w-7xl px-6 py-10 lg:px-10">
        <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div>
            <p className="font-display text-lg text-espresso">HI-Natya Verse</p>
            <p className="mt-1 text-sm text-espresso-faint">Where Dance Becomes Story</p>
          </div>
          <p className="max-w-sm text-xs leading-relaxed text-espresso-faint">
            A research-oriented, multimodal AI system for interpreting Bharatanatyam performances.
            Every result shown here is grounded in evidence produced by the connected AI backend.
          </p>
        </div>
        <div className="mt-8 rule-gold" />
        <p className="mt-6 text-xs text-espresso-faint">
          Final-year AI project · Mudra · Bhava · Pose · Audio · Evidence · Story
        </p>
      </div>
    </footer>
  )
}
