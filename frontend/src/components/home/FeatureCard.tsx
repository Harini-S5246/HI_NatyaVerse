import type { LucideIcon } from 'lucide-react'

interface FeatureCardProps {
  icon: LucideIcon
  title: string
  description: string
}

export default function FeatureCard({ icon: Icon, title, description }: FeatureCardProps) {
  return (
    <div className="card-surface group p-7 transition-shadow duration-300 hover:shadow-lift">
      <div className="flex h-11 w-11 items-center justify-center rounded-full border border-vermilion-500/25 text-vermilion-500 transition-colors group-hover:bg-vermilion-50">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <h3 className="mt-5 text-lg text-espresso">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-espresso-light">{description}</p>
    </div>
  )
}
