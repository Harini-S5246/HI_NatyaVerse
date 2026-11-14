import { useState } from 'react'
import type { DanceVisualReference, SceneVisualReferences } from '@/types/storyToDance'
import { API_BASE_URL } from '@/services/api'

interface SceneVisualReferencesProps {
  references: SceneVisualReferences | null
  status: 'loading' | 'loaded' | 'error'
  error: string | null
}

const EMPTY_REFERENCE: DanceVisualReference = {
  category: 'mudra',
  status: 'unavailable',
  source_type: 'unavailable',
  reference_status: 'unavailable',
  concept: null,
  predicted_label: null,
  dataset_label: null,
  confidence: null,
  confidence_threshold: 0.65,
  video_id: null,
  frame_number: null,
  timestamp: null,
  frame_filename: null,
  image_url: null,
  original_frame_url: null,
  asset_id: null,
  dataset_name: null,
  dataset_relative_path: null,
  evidence_status: 'Reference unavailable — dataset evidence not found.',
  crop_status: 'not_applicable',
  unavailable_reason: 'Reference lookup has not completed.',
  reused_in_scenes: [],
}

function formatTimestamp(timestamp: number): string {
  const minutes = Math.floor(timestamp / 60)
  const seconds = (timestamp % 60).toFixed(1).padStart(4, '0')
  return `${minutes}:${seconds}`
}

function resolveImageUrl(path: string | null): string | null {
  return path ? new URL(path, API_BASE_URL).toString() : null
}

function referenceStatusLabel(reference: DanceVisualReference): string {
  switch (reference.reference_status) {
    case 'model_predicted':
      return 'Model-predicted'
    case 'dataset_labelled':
      return 'Dataset-labelled'
    case 'expert_verified':
      return 'Expert-verified'
    default:
      return 'Unavailable'
  }
}

function sourceLabel(reference: DanceVisualReference): string {
  switch (reference.source_type) {
    case 'analyzed_video':
      return 'Analysed video frame'
    case 'project_dataset':
      return 'Project dataset reference example'
    default:
      return 'Unavailable'
  }
}

function cropDescription(reference: DanceVisualReference): string {
  if (reference.crop_status === 'face_detector_crop') {
    return 'Face region localized from the original analysed frame.'
  }
  if (reference.crop_status === 'full_source_frame_no_hand_landmarks') {
    return 'Full source frame shown; hand landmarks were not saved, so no hand crop is claimed.'
  }
  if (reference.crop_status === 'dataset_image') {
    return 'Original labelled dataset image; no synthetic crop or alteration.'
  }
  return 'Original source frame shown without a category-specific crop.'
}

function ReferenceCard({
  title,
  reference,
  loading,
}: {
  title: string
  reference: DanceVisualReference
  loading: boolean
}) {
  const [imageUnavailable, setImageUnavailable] = useState(false)
  const imageSrc = resolveImageUrl(reference.image_url)
  const originalHref = resolveImageUrl(reference.original_frame_url) ?? imageSrc
  const imageAvailable = reference.status === 'matched'
    && Boolean(imageSrc)
    && Boolean(originalHref)
    && !imageUnavailable
  const displayLabel = reference.predicted_label
    ?? reference.dataset_label
    ?? reference.concept

  return (
    <section className="min-w-0 rounded-sm border border-line bg-parchment-50 p-4" aria-label={title}>
      <h4 className="text-sm font-semibold text-espresso">{title}</h4>
      {imageAvailable ? (
        <a
          href={originalHref ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="mt-3 block rounded-sm border border-line bg-black p-1"
          aria-label={`Open original reference image for ${title}`}
        >
          <img
            src={imageSrc ?? undefined}
            alt={`${sourceLabel(reference)} for ${displayLabel ?? title}`}
            className="max-h-80 w-full object-contain"
            loading="lazy"
            onError={() => setImageUnavailable(true)}
          />
        </a>
      ) : (
        <div className="mt-3 flex min-h-40 items-center justify-center rounded-sm border border-dashed border-line bg-white px-4 text-center text-sm text-espresso-faint">
          {loading
            ? 'Searching saved analyses and labelled project datasets…'
            : 'Reference unavailable — dataset evidence not found.'}
        </div>
      )}

      {loading ? (
        <p className="mt-3 text-xs text-espresso-faint">Looking up saved Dance → Story evidence and labelled datasets.</p>
      ) : reference.status === 'matched' && !imageUnavailable ? (
        <>
          <p className="mt-3 text-sm font-medium text-grounded">
            {displayLabel ?? title}
          </p>
          <span className="mt-2 inline-flex rounded-full bg-grounded-bg px-2.5 py-1 text-xs text-grounded">
            {referenceStatusLabel(reference)}
          </span>
          {reference.source_type === 'analyzed_video' && reference.confidence !== null && (
            <p className="mt-1 text-xs text-espresso-light">
              Confidence: {(reference.confidence * 100).toFixed(1)}%
              {' · '}minimum {Math.round(reference.confidence_threshold * 100)}%
            </p>
          )}
          {reference.video_id && (
            <p className="mt-1 break-all text-xs text-espresso-light">
              Source video ID: {reference.video_id}
            </p>
          )}
          {reference.timestamp !== null && (
            <p className="mt-1 text-xs text-espresso-light">
              Timestamp: {formatTimestamp(reference.timestamp)}
              {reference.frame_number !== null ? ` · Frame ${reference.frame_number}` : ''}
            </p>
          )}
          {reference.dataset_name && (
            <p className="mt-1 text-xs text-espresso-light">
              Dataset: {reference.dataset_name}
            </p>
          )}
          {reference.dataset_relative_path && (
            <p className="mt-1 break-all text-xs text-espresso-faint">
              Dataset image: {reference.dataset_relative_path}
            </p>
          )}
          <p className="mt-2 text-xs text-espresso-faint">{sourceLabel(reference)}</p>
          <p className="mt-1 text-xs text-espresso-faint">{cropDescription(reference)}</p>
          <p className="mt-1 text-xs text-espresso-faint">{reference.evidence_status}</p>
          {(reference.reused_in_scenes?.length ?? 0) > 0 && (
            <p className="mt-2 text-xs text-espresso-faint">
              This same reference is also selected for another scene; no distinct matching image was available.
            </p>
          )}
          <p className="mt-2 text-xs text-vermilion-500">Open image to view the source image at full size.</p>
        </>
      ) : (
        <p className="mt-3 text-xs text-espresso-faint">
          {imageUnavailable
            ? 'The saved source image could not be loaded.'
            : (
              <>
                {reference.concept && (
                  <span className="mb-1 block">Requested supported concept: {reference.concept}</span>
                )}
                <span>{reference.unavailable_reason ?? reference.evidence_status}</span>
              </>
            )}
        </p>
      )}
    </section>
  )
}

export default function SceneVisualReferences({
  references,
  status,
  error,
}: SceneVisualReferencesProps) {
  const threshold = references?.confidence_threshold ?? EMPTY_REFERENCE.confidence_threshold
  const sections = [
    { title: 'Mudra Reference Image', reference: references?.mudra ?? { ...EMPTY_REFERENCE, category: 'mudra' as const } },
    { title: 'Bhava Reference Image', reference: references?.bhava ?? { ...EMPTY_REFERENCE, category: 'bhava' as const } },
    { title: 'Bharatanatyam Pose Reference Image', reference: references?.pose ?? { ...EMPTY_REFERENCE, category: 'pose' as const } },
  ]

  return (
    <div className="mt-5">
      <p className="mb-3 text-xs text-espresso-faint">
        References use only saved analysed Dance → Story evidence and labelled project datasets. Model predictions are not ground truth or expert-verified. Video confidence threshold: {Math.round(threshold * 100)}%.
      </p>
      {status === 'error' && (
        <p role="alert" className="mb-3 text-sm text-unresolved">
          Reference lookup failed: {error}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        {sections.map((section) => (
          <ReferenceCard
            key={section.reference.category}
            title={section.title}
            reference={section.reference}
            loading={status === 'loading'}
          />
        ))}
      </div>
    </div>
  )
}
