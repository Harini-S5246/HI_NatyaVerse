/**
 * Frame detail panel component.
 * 
 * Shows detailed information for a selected frame including:
 * - Frame image
 * - Predictions (mudra, bhava, pose)
 * - Knowledge base information for mudra
 * - Confidence metrics
 */
import { X } from 'lucide-react'
import { formatDuration, formatPercent } from '@/utils/format'
import { getFrameImageUrl } from '@/services/api'
import type { FrameLevelAnalysis } from '@/types/analysis'
import GroundingBadge from '@/components/evidence/GroundingBadge'

interface FrameDetailPanelProps {
  videoId: string
  frame: FrameLevelAnalysis | null
  onClose?: () => void
}

export default function FrameDetailPanel({
  videoId,
  frame,
  onClose,
}: FrameDetailPanelProps) {
  if (!frame) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end bg-black/25 backdrop-blur-sm">
      {/* Close on background click */}
      <button
        type="button"
        onClick={onClose}
        className="absolute inset-0"
        aria-label="Close frame detail panel"
      />

      {/* Panel */}
      <div className="relative w-full max-w-md h-screen overflow-y-auto bg-background shadow-lg">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-background px-6 py-4">
          <div>
            <p className="text-xs text-espresso-faint font-mono">
              Frame {String(frame.frame_number).padStart(6, '0')}
            </p>
            <p className="text-sm font-medium text-espresso">
              {formatDuration(frame.timestamp)}
            </p>
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-espresso-light hover:text-espresso transition-colors"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Frame image */}
          <div>
            <p className="eyebrow mb-3">Frame Image</p>
            <img
              src={getFrameImageUrl(videoId, frame.filename)}
              alt={`Frame ${frame.frame_number}`}
              className="w-full aspect-video object-cover rounded-lg bg-espresso-faint"
            />
            <p className="text-xs text-espresso-faint mt-2">{frame.filename}</p>
          </div>

          {/* Metadata */}
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-espresso-faint">Timestamp</span>
              <span className="text-espresso font-medium">{formatDuration(frame.timestamp)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-espresso-faint">Frame Number</span>
              <span className="text-espresso font-mono font-medium">
                {String(frame.frame_number).padStart(6, '0')}
              </span>
            </div>
          </div>

          {/* Mudra */}
          <div className="border-t border-line pt-4">
            <p className="eyebrow mb-3">Mudra</p>
            <div className="space-y-3">
              <div>
                <p className="text-base font-medium text-espresso">
                  {frame.mudra.label || 'Not detected'}
                </p>
                {frame.mudra.status === 'detected' && frame.mudra.label && (
                  <GroundingBadge status="unresolved" size="sm" />
                )}
              </div>

              {/* Confidence bar */}
              {frame.mudra.confidence !== null && (
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <p className="text-xs text-espresso-faint">Confidence</p>
                    <p className="text-sm font-medium text-espresso">
                      {formatPercent(frame.mudra.confidence)}
                    </p>
                  </div>
                  <div className="h-2 bg-line rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent transition-all"
                      style={{ width: `${Math.min(100, (frame.mudra.confidence ?? 0) * 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Knowledge base information */}
              {frame.mudra.label && (
                <div className="bg-espresso-faint/5 rounded-lg p-3 space-y-2">
                  {frame.mudra.meaning &&
                    ['verified', 'partially_verified'].includes(frame.mudra.verification_status ?? '') &&
                    frame.mudra.knowledge_status === frame.mudra.verification_status &&
                    frame.mudra.claim_id &&
                    frame.mudra.source_references?.length ? (
                    <>
                      <p className="text-xs font-medium text-accent">
                        {frame.mudra.verification_status?.replaceAll('_', ' ')}
                      </p>
                      <p className="text-sm text-espresso">
                        {frame.mudra.meaning}
                      </p>
                      <p className="text-xs text-espresso-faint">Claim: {frame.mudra.claim_id}</p>
                      {frame.mudra.source_references.map((reference) => (
                        <p key={reference} className="text-xs text-espresso-faint">Source: {reference}</p>
                      ))}
                      {frame.mudra.uncertainty_notes?.map((note) => (
                        <p key={note} className="text-xs text-espresso-faint">Uncertainty: {note}</p>
                      ))}
                    </>
                  ) : (
                    <>
                      <p className="text-xs font-medium text-espresso-faint">Information Status</p>
                      <p className="text-sm text-espresso-faint">
                        Meaning withheld or unavailable
                      </p>
                    </>
                  )}
                  {frame.mudra.uncertainty_reason && (
                    <p className="text-xs text-espresso-faint">{frame.mudra.uncertainty_reason}</p>
                  )}
                  {frame.mudra.explanation && (
                    <p className="text-xs text-espresso-faint">{frame.mudra.explanation}</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Bhava */}
          <div className="border-t border-line pt-4">
            <p className="eyebrow mb-3">Facial-expression observation</p>
            <div className="space-y-3">
              <div>
                <p className="text-base font-medium text-espresso">
                  {frame.bhava.label || 'Not detected'}
                </p>
                <p className="text-xs text-espresso-faint">Predicted emotion label; not a classical Bhava or Rasa classification.</p>
              </div>

              {frame.bhava.confidence !== null && (
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <p className="text-xs text-espresso-faint">Confidence</p>
                    <p className="text-sm font-medium text-espresso">
                      {formatPercent(frame.bhava.confidence)}
                    </p>
                  </div>
                  <div className="h-2 bg-line rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent transition-all"
                      style={{ width: `${Math.min(100, (frame.bhava.confidence ?? 0) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Pose */}
          <div className="border-t border-line pt-4">
            <p className="eyebrow mb-3">Pose</p>
            {frame.pose.status === 'unavailable' ? (
              <p className="text-sm text-espresso-faint">Pose unavailable in current pipeline</p>
            ) : (
              <div className="space-y-3">
                <div>
                  <p className="text-base font-medium text-espresso">
                    {frame.pose.label || 'Not detected'}
                  </p>
                </div>

                {frame.pose.confidence !== null && (
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <p className="text-xs text-espresso-faint">Confidence</p>
                      <p className="text-sm font-medium text-espresso">
                        {formatPercent(frame.pose.confidence)}
                      </p>
                    </div>
                    <div className="h-2 bg-line rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all"
                        style={{ width: `${Math.min(100, (frame.pose.confidence ?? 0) * 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
