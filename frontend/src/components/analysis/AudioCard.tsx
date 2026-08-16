import { AudioLines } from 'lucide-react'
import type { AudioAnalysis } from '@/types/analysis'
import { formatPercent } from '@/utils/format'

interface AudioCardProps {
  audio?: AudioAnalysis
}

export default function AudioCard({ audio }: AudioCardProps) {
  if (!audio) {
    return (
      <div className="card-surface p-6">
        <p className="eyebrow">Audio</p>
        <p className="mt-4 text-sm text-espresso-faint">No audio analysis was reported by the backend.</p>
      </div>
    )
  }

  const isRhythmicOnly = audio.audio_type === 'rhythmic-only' || audio.lyrics_available === false

  return (
    <div className="card-surface p-6">
      <div className="flex items-center justify-between">
        <p className="eyebrow">Audio</p>
        <AudioLines className="h-4 w-4 text-vermilion-500" aria-hidden="true" />
      </div>

      {audio.audio_type && <p className="mt-3 text-sm text-espresso">{audio.audio_type}</p>}
      {audio.audio_status && <p className="mt-1 text-xs text-espresso-faint">{audio.audio_status}</p>}

      {isRhythmicOnly ? (
        <div className="mt-4 rounded-sm border border-unresolved/30 bg-unresolved-bg px-4 py-3">
          <p className="text-sm font-medium text-unresolved">Rhythmic-only audio</p>
          <p className="mt-1 text-xs text-espresso-light">Meaningful lyric evidence unavailable.</p>
        </div>
      ) : (
        (audio.lyrics || audio.transcription) && (
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-xs uppercase tracking-wide text-espresso-faint">Transcription</p>
            <p className="mt-2 text-sm leading-relaxed text-espresso-light">
              {audio.lyrics ?? audio.transcription}
            </p>
          </div>
        )
      )}

      {audio.audio_confidence !== undefined && (
        <p className="mt-4 text-xs text-espresso-faint">{formatPercent(audio.audio_confidence)}</p>
      )}
    </div>
  )
}
