import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Pause, Play, RotateCcw } from 'lucide-react'
import type { ChoreographyStep } from '@/types/storyToDance'

interface Landmark {
  x: number
  y: number
}

interface VisualizationFrame {
  frame_index: number
  body_landmarks: Record<string, Landmark>
  translation_x: number
  rotation_degrees: number
}

interface VisualizationScene {
  scene_id: string
  action: string
  movement_concept: string | null
  movement_concepts: string[]
  direction: string | null
  duration_seconds: number
  mapping_status: 'prototype_available' | 'review_required'
  poses: VisualizationFrame[]
}

const FRAME_DELAY_MS = 350
const SKELETON_LINES = [
  ['head', 'neck'],
  ['neck', 'left_shoulder'],
  ['neck', 'right_shoulder'],
  ['left_shoulder', 'left_elbow'],
  ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'],
  ['right_elbow', 'right_wrist'],
  ['neck', 'hip'],
  ['hip', 'left_knee'],
  ['left_knee', 'left_ankle'],
  ['hip', 'right_knee'],
  ['right_knee', 'right_ankle'],
] as const

function bodyLandmarks(stepIndex: number): Record<string, Landmark> {
  const stepLeg = stepIndex % 2 === 0 ? 1 : -1
  return {
    head: { x: 50, y: 12 },
    neck: { x: 50, y: 25 },
    left_shoulder: { x: 40, y: 29 },
    right_shoulder: { x: 60, y: 29 },
    left_elbow: { x: 31, y: 39 },
    left_wrist: { x: 26, y: 48 },
    right_elbow: { x: 69, y: 39 },
    right_wrist: { x: 74, y: 48 },
    hip: { x: 50, y: 56 },
    left_knee: { x: 44 - stepLeg * 3, y: 72 },
    left_ankle: { x: 42 - stepLeg * 7, y: 91 },
    right_knee: { x: 56 + stepLeg * 3, y: 72 },
    right_ankle: { x: 58 + stepLeg * 7, y: 91 },
  }
}

function createVisualizationSequence(steps: ChoreographyStep[]): VisualizationScene[] {
  return [...steps]
    .sort((left, right) => left.order - right.order)
    .map((step) => {
      const intent = step.movement_intent
      const movement = intent?.movement_concept
      const frameCount = movement === 'Chari' ? 8 : movement === 'Bhramari' ? 9 : 0
      const poses = Array.from({ length: frameCount }, (_, frameIndex) => ({
        frame_index: frameIndex,
        body_landmarks: bodyLandmarks(frameIndex),
        translation_x: movement === 'Chari' ? frameIndex * 2.5 : 0,
        rotation_degrees: movement === 'Bhramari' ? frameIndex * 45 : 0,
      }))

      return {
        scene_id: step.scene_id,
        action: intent?.actions.length
          ? intent.actions.map((action) => action.action).join(' → ')
          : intent?.action ?? step.story_action,
        movement_concept: movement ?? null,
        movement_concepts: intent?.actions.length
          ? intent.actions
            .filter((action) => action.mapping_status === 'supported_concept' && action.movement_concept)
            .map((action) => `${action.movement_concept} (${action.action})`)
          : movement ? [movement] : [],
        direction: intent?.actions.length
          ? intent.actions.map((action) => action.direction ?? '—').join(' → ')
          : intent?.direction ?? null,
        duration_seconds: frameCount ? (frameCount * FRAME_DELAY_MS) / 1000 : 0,
        mapping_status: frameCount ? 'prototype_available' : 'review_required',
        poses,
      }
    })
}

function StickFigure({ frame }: { frame: VisualizationFrame }) {
  const points = frame.body_landmarks
  return (
    <svg
      viewBox="0 0 100 100"
      role="img"
      aria-label={`Generic movement visualization frame ${frame.frame_index + 1}`}
      className="h-64 w-48 overflow-visible"
    >
      <g transform={`translate(${frame.translation_x} 0) rotate(${frame.rotation_degrees} 50 56)`}>
        {SKELETON_LINES.map(([from, to]) => (
          <line
            key={`${from}-${to}`}
            x1={points[from].x}
            y1={points[from].y}
            x2={points[to].x}
            y2={points[to].y}
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        ))}
        <circle
          cx={points.head.x}
          cy={points.head.y}
          r="6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        {Object.entries(points)
          .filter(([name]) => name !== 'head')
          .map(([name, point]) => (
            <circle key={name} cx={point.x} cy={point.y} r="1.7" fill="currentColor" />
          ))}
      </g>
    </svg>
  )
}

export default function GeneratedDanceVisualization({ steps }: { steps: ChoreographyStep[] }) {
  const sequence = useMemo(() => createVisualizationSequence(steps), [steps])
  const [sceneIndex, setSceneIndex] = useState(0)
  const [frameIndex, setFrameIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const scene = sequence[sceneIndex]
  const pose = scene?.poses[frameIndex]

  useEffect(() => {
    setSceneIndex(0)
    setFrameIndex(0)
    setPlaying(false)
  }, [sequence])

  useEffect(() => {
    if (!playing || !scene) return undefined
    const timer = window.setTimeout(() => {
      if (frameIndex + 1 < scene.poses.length) {
        setFrameIndex(frameIndex + 1)
      } else if (sceneIndex + 1 < sequence.length) {
        setSceneIndex(sceneIndex + 1)
        setFrameIndex(0)
      } else {
        setPlaying(false)
      }
    }, FRAME_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [frameIndex, playing, scene, sceneIndex, sequence])

  const selectScene = (index: number) => {
    setSceneIndex(Math.max(0, Math.min(index, sequence.length - 1)))
    setFrameIndex(0)
  }

  if (!scene) return null

  return (
    <section className="card-surface p-6 sm:p-8" aria-label="Technical Movement Preview">
      <p className="eyebrow">Technical preview</p>
      <h2 className="mt-2 font-display text-2xl">Choreography Preview</h2>
      <p className="mt-2 text-sm text-espresso-light">
        Schematic SVG for choreography inspection only. This is not the generated dance performance, a generated pose sequence, or an authentic Bharatanatyam performance.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="flex min-h-72 items-center justify-center overflow-hidden rounded-sm border border-line bg-parchment-50 text-vermilion-500">
          {pose ? (
            <StickFigure frame={pose} />
          ) : (
            <p className="max-w-xs px-6 text-center text-sm text-espresso-light">
              No validated schematic movement mapping is available for this scene.
            </p>
          )}
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-display text-xl">Scene {sceneIndex + 1} / {sequence.length}</p>
          <p>
            <span className="font-medium">Source-supported concept:</span>{' '}
            {scene.movement_concepts.length ? scene.movement_concepts.join(', ') : 'Review required'}
          </p>
          <p><span className="font-medium">Action:</span> {scene.action}</p>
          <p><span className="font-medium">Direction:</span> {scene.direction ?? '—'}</p>
          <p><span className="font-medium">Status:</span> {scene.mapping_status === 'prototype_available' ? 'Prototype schematic available' : 'Review required'}</p>
          {scene.poses.length > 0 && (
            <p className="text-xs text-espresso-faint">
              Prototype playback duration: {scene.duration_seconds.toFixed(1)} s
            </p>
          )}
          {pose && (
            <p className="text-xs text-espresso-faint">
              Frame {frameIndex + 1} / {scene.poses.length} · {Object.keys(pose.body_landmarks).length} schematic landmarks
            </p>
          )}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary" onClick={() => setPlaying(!playing)} disabled={!scene.poses.length && !sequence.some((item) => item.poses.length)}>
          {playing ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type="button" className="btn-secondary" onClick={() => { setPlaying(false); selectScene(0) }}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" /> Restart
        </button>
        <button type="button" className="btn-secondary" onClick={() => { setPlaying(false); selectScene(sceneIndex - 1) }} disabled={sceneIndex === 0}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Previous scene
        </button>
        <button type="button" className="btn-secondary" onClick={() => { setPlaying(false); selectScene(sceneIndex + 1) }} disabled={sceneIndex === sequence.length - 1}>
          Next scene <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </section>
  )
}
