import { AlertTriangle, RotateCcw } from 'lucide-react'
import type { ApiErrorPayload } from '@/types/analysis'

interface ErrorMessageProps {
  error: ApiErrorPayload | string
  onRetry?: () => void
}

export default function ErrorMessage({ error, onRetry }: ErrorMessageProps) {
  const message = typeof error === 'string' ? error : error.message

  return (
    <div className="flex flex-col items-center gap-4 rounded-card border border-danger/30 bg-danger-bg px-6 py-10 text-center">
      <AlertTriangle className="h-8 w-8 text-danger" aria-hidden="true" />
      <p className="max-w-md text-sm text-espresso">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary">
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  )
}
