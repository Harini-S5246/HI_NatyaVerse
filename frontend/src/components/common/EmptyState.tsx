import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  actionLabel?: string
  actionTo?: string
}

export default function EmptyState({ icon, title, description, actionLabel, actionTo }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-line bg-parchment-100/60 px-6 py-20 text-center">
      {icon && <div className="mb-5 text-gold-500">{icon}</div>}
      <h3 className="font-display text-2xl text-espresso">{title}</h3>
      {description && <p className="mt-2 max-w-md text-sm text-espresso-light">{description}</p>}
      {actionLabel && actionTo && (
        <Link to={actionTo} className="btn-primary mt-6">
          {actionLabel}
        </Link>
      )}
    </div>
  )
}
