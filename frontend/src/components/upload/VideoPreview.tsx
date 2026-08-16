import { useEffect, useState } from 'react'
import { Trash2, Sparkles } from 'lucide-react'
import { formatDuration, formatFileSize } from '@/utils/format'

interface VideoPreviewProps {
  file: File
  onRemove: () => void
  onAnalyze: () => void
  isSubmitting?: boolean
}

export default function VideoPreview({ file, onRemove, onAnalyze, isSubmitting }: VideoPreviewProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [duration, setDuration] = useState<number | null>(null)

  useEffect(() => {
    const url = URL.createObjectURL(file)
    setObjectUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  return (
    <div className="card-surface overflow-hidden">
      <div className="border-b border-line px-6 py-4">
        <p className="eyebrow">Video preview</p>
      </div>

      <div className="bg-espresso">
        {objectUrl && (
          <video
            src={objectUrl}
            controls
            className="mx-auto max-h-[420px] w-full bg-black"
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
          />
        )}
      </div>

      <div className="flex flex-col gap-4 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-espresso">{file.name}</p>
          <p className="mt-1 text-xs text-espresso-faint">
            {formatFileSize(file.size)}
            {duration !== null && ` · ${formatDuration(duration)}`}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button type="button" onClick={onRemove} className="btn-secondary" disabled={isSubmitting}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Remove
          </button>
          <button type="button" onClick={onAnalyze} className="btn-primary" disabled={isSubmitting}>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            {isSubmitting ? 'Uploading…' : 'Analyze Performance'}
          </button>
        </div>
      </div>
    </div>
  )
}
