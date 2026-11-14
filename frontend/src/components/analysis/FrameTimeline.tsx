/**
 * Frame-level timeline component.
 * 
 * Displays frame-by-frame predictions for mudra, bhava, and pose
 * with frame thumbnails, timestamps, and confidence scores.
 */
import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { formatDuration, formatPercent } from '@/utils/format'
import { getFrameImageUrl } from '@/services/api'
import type { FrameAnalysisEvent, FrameLevelAnalysis } from '@/types/analysis'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface FrameTimelineProps {
  videoId: string
  frames: FrameLevelAnalysis[]
  events?: {
    mudra: FrameAnalysisEvent[]
    bhava: FrameAnalysisEvent[]
    pose: FrameAnalysisEvent[]
  }
  eventModalities?: Array<'mudra' | 'bhava' | 'pose'>
  onFrameSelect?: (frame: FrameLevelAnalysis) => void
}

export default function FrameTimeline({ videoId, frames, events, eventModalities = ['mudra', 'bhava', 'pose'], onFrameSelect }: FrameTimelineProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const toggleExpanded = (frameNumber: number) => {
    const next = new Set(expanded)
    if (next.has(frameNumber)) {
      next.delete(frameNumber)
    } else {
      next.add(frameNumber)
    }
    setExpanded(next)
  }

  const handleFrameClick = (frame: FrameLevelAnalysis) => {
    toggleExpanded(frame.frame_number)
    if (onFrameSelect) {
      onFrameSelect(frame)
    }
  }

  if (frames.length === 0) {
    return <p className="text-sm text-espresso-faint">No frames analyzed.</p>
  }

  const eventItems = eventModalities
    .flatMap((modality) => events?.[modality] ?? [])
    .filter((event) => event.label)
    .sort((a, b) => a.start_timestamp - b.start_timestamp)
  const displayFrames = frames.length > 100 ? frames.filter((_, i) => i % 5 === 0) : frames

  return (
    <div className="space-y-2">
      {eventItems.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-espresso-faint">Detected events</p>
          <div className="divide-y divide-line border border-line rounded-lg overflow-hidden bg-card-surface">
            {eventItems.map((event, index) => {
              const frame = event.representative_frame
              return (
                <button
                  key={`${event.modality}-${event.first_frame_number}-${index}`}
                  type="button"
                  onClick={() => onFrameSelect?.(frame)}
                  className="w-full text-left hover:bg-card-hover transition-colors p-4 flex items-center gap-4"
                >
                  <img
                    src={getFrameImageUrl(videoId, frame.filename)}
                    alt={`Representative frame ${frame.frame_number}`}
                    className="h-16 w-24 shrink-0 object-cover rounded bg-espresso-faint"
                    loading="lazy"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="eyebrow">{event.modality}</p>
                    <p className="text-base font-medium text-espresso">{event.label}</p>
                    <p className="text-xs text-espresso-faint">
                      {formatDuration(event.start_timestamp)}–{formatDuration(event.end_timestamp)} · {event.frame_count} frames
                    </p>
                    <p className="text-xs text-espresso-faint">
                      Average confidence: {event.average_confidence === null ? '—' : formatPercent(event.average_confidence)} · Frame {frame.frame_number}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}
      <details className="border border-line rounded-lg bg-card-surface">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-espresso">
          Show all frames ({frames.length})
        </summary>
        <div className="p-4 pt-0 space-y-2">
          <p className="text-xs text-espresso-faint">
            Showing {displayFrames.length} of {frames.length} frames
            {frames.length > displayFrames.length && ' (sampled every 5th frame)'}
          </p>
          <div className="divide-y divide-line border border-line rounded-lg overflow-hidden bg-card-surface">
        {displayFrames.map((frame) => (
          <div key={`${frame.frame_number}`} className="border-0">
            {/* Frame header - clickable */}
            <button
              type="button"
              onClick={() => handleFrameClick(frame)}
              className="w-full text-left hover:bg-card-hover transition-colors p-4 flex items-center justify-between gap-4"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <p className="text-xs text-espresso-faint font-mono">
                    {String(frame.frame_number).padStart(6, '0')}
                  </p>
                  <p className="text-sm text-espresso font-medium">
                    {formatDuration(frame.timestamp)}
                  </p>
                </div>

                {/* Quick preview of predictions */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="eyebrow text-xs">Mudra</p>
                    <p className="text-espresso">
                      {frame.mudra.label || '—'}
                    </p>
                    {frame.mudra.confidence !== null && (
                      <p className="text-xs text-espresso-faint">
                        {formatPercent(frame.mudra.confidence)}
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="eyebrow text-xs">Facial-expression observation</p>
                    <p className="text-espresso">
                      {frame.bhava.label || '—'}
                    </p>
                    {frame.bhava.confidence !== null && (
                      <p className="text-xs text-espresso-faint">
                        {formatPercent(frame.bhava.confidence)}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Thumbnail and expand indicator */}
              <div className="flex items-center gap-3">
                <img
                  src={getFrameImageUrl(videoId, frame.filename)}
                  alt={`Frame ${frame.frame_number}`}
                  className="h-12 w-12 object-cover rounded bg-espresso-faint"
                  loading="lazy"
                />
                <div className="text-espresso-light">
                  {expanded.has(frame.frame_number) ? (
                    <ChevronUp className="h-5 w-5" />
                  ) : (
                    <ChevronDown className="h-5 w-5" />
                  )}
                </div>
              </div>
            </button>

            {/* Expanded details */}
            {expanded.has(frame.frame_number) && (
              <div className="bg-espresso-faint/5 p-4 space-y-4 border-t border-line">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  {/* Mudra details */}
                  <div className="space-y-2">
                    <p className="eyebrow">Mudra</p>
                    <div className="space-y-1">
                      <p className="text-base font-medium text-espresso">
                        {frame.mudra.label || 'Not detected'}
                      </p>
                      {frame.mudra.confidence !== null && (
                        <>
                          <div className="h-2 bg-line rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${Math.min(100, (frame.mudra.confidence ?? 0) * 100)}%` }}
                            />
                          </div>
                          <p className="text-xs text-espresso-faint">
                            {formatPercent(frame.mudra.confidence)}
                          </p>
                        </>
                      )}
                      {frame.mudra.status === 'detected' && (
                        <GroundingBadge status="unresolved" size="sm" />
                      )}
                    </div>
                  </div>

                  {/* Generic facial-expression model output */}
                  <div className="space-y-2">
                    <p className="eyebrow">Facial-expression observation</p>
                    <div className="space-y-1">
                      <p className="text-base font-medium text-espresso">
                        {frame.bhava.label || 'Not detected'}
                      </p>
                      <p className="text-xs text-espresso-faint">Predicted emotion label; not a classical Bhava or Rasa classification.</p>
                      {frame.bhava.confidence !== null && (
                        <>
                          <div className="h-2 bg-line rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${Math.min(100, (frame.bhava.confidence ?? 0) * 100)}%` }}
                            />
                          </div>
                          <p className="text-xs text-espresso-faint">
                            {formatPercent(frame.bhava.confidence)}
                          </p>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Pose details */}
                  <div className="space-y-2">
                    <p className="eyebrow">Pose</p>
                    <div className="space-y-1">
                      {frame.pose.status === 'unavailable' ? (
                        <p className="text-xs text-espresso-faint italic">
                          Not available in current pipeline
                        </p>
                      ) : (
                        <>
                          <p className="text-base font-medium text-espresso">
                            {frame.pose.label || 'Not detected'}
                          </p>
                          {frame.pose.confidence !== null && (
                            <>
                              <div className="h-2 bg-line rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-accent"
                                  style={{ width: `${Math.min(100, (frame.pose.confidence ?? 0) * 100)}%` }}
                                />
                              </div>
                              <p className="text-xs text-espresso-faint">
                                {formatPercent(frame.pose.confidence)}
                              </p>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Frame metadata */}
                <div className="text-xs text-espresso-faint space-y-1 border-t border-line pt-3">
                  <p>Frame: {frame.frame_number}</p>
                  <p>Time: {formatDuration(frame.timestamp)}</p>
                  <p>File: {frame.filename}</p>
                </div>
              </div>
            )}
          </div>
        ))}
          </div>
        </div>
      </details>
    </div>
  )
}
