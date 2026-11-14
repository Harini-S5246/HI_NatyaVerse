import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import AnalysisOverview from '@/components/analysis/AnalysisOverview'
import FrameTimeline from '@/components/analysis/FrameTimeline'
import FrameDetailPanel from '@/components/analysis/FrameDetailPanel'
import EvidencePanel from '@/components/evidence/EvidencePanel'
import NarrativeEvidenceReview from '@/components/evidence/NarrativeEvidenceReview'
import EvidenceStatus from '@/components/evidence/EvidenceStatus'
import EvidenceProvenancePanel from '@/components/evidence/EvidenceProvenancePanel'
import EvidenceProvenanceTimeline from '@/components/evidence/EvidenceProvenanceTimeline'
import SectionHeading from '@/components/common/SectionHeading'
import LoadingState from '@/components/common/LoadingState'
import ErrorMessage from '@/components/common/ErrorMessage'
import EmptyState from '@/components/common/EmptyState'
import { getCanonicalAnalysis, getFrameLevelAnalysis } from '@/services/api'
import { formatDuration, formatPercent } from '@/utils/format'
import { hasBhavaModelObservation, hasMudraModelObservation, hasTechnicalAudioEvidence } from '@/utils/evidenceStatus'
import type { ApiErrorPayload, CanonicalAnalysis, SupportedLanguage, FrameLevelAnalysisResponse, FrameLevelAnalysis } from '@/types/analysis'

interface AnalysisProps { language: SupportedLanguage; onLanguageChange: (language: SupportedLanguage) => void }

export default function Analysis({}: AnalysisProps) {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [analysis, setAnalysis] = useState<CanonicalAnalysis | null>(null)
  const [frameLevelAnalysis, setFrameLevelAnalysis] = useState<FrameLevelAnalysisResponse | null>(null)
  const [selectedFrame, setSelectedFrame] = useState<FrameLevelAnalysis | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [frameError, setFrameError] = useState<ApiErrorPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingFrames, setLoadingFrames] = useState(false)

  const load = async () => {
    if (!analysisId) return
    setLoading(true); setError(null)
    try { 
      setAnalysis(await getCanonicalAnalysis(analysisId)) 
    } catch (err) { 
      setError(err as ApiErrorPayload) 
    } finally { 
      setLoading(false) 
    }
  }

  const loadFrameLevelAnalysis = async () => {
    if (!analysisId) return
    setLoadingFrames(true)
    setFrameError(null)
    try {
      const result = await getFrameLevelAnalysis(analysisId)
      setFrameLevelAnalysis(result)
    } catch (err) {
      setFrameError(err as ApiErrorPayload)
      // This is optional, so don't block the main analysis
    } finally {
      setLoadingFrames(false)
    }
  }

  useEffect(() => { 
    void load() 
  }, [analysisId])

  useEffect(() => {
    if (analysis) {
      void loadFrameLevelAnalysis()
    }
  }, [analysis])

  if (!analysisId) return <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10"><EmptyState title="No performance analyzed yet." description="Upload a Bharatanatyam performance to see its multimodal analysis here." actionLabel="Analyze a Performance" actionTo="/analyze" /></div>
  if (loading) return <LoadingState label="Loading analysis…" />
  if (error) return <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10"><ErrorMessage error={error} onRetry={load} /></div>
  if (!analysis) return <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10"><EmptyState title="No result found." description="This analysis could not be located on the backend." actionLabel="Analyze a Performance" actionTo="/analyze" /></div>

  const evidence = analysis.fusion.evidence
  const mudraEvents = frameLevelAnalysis?.events?.mudra ?? []
  const bhavaEvents = frameLevelAnalysis?.events?.bhava ?? []
  const uniqueMudras = Array.from(new Map((analysis.mudra.mudra?.detections ?? []).map((item) => [item.name, item])).values())
  const highestMudraConfidence = mudraEvents.reduce((highest, event) => Math.max(highest, event.average_confidence ?? 0), 0)
  const highestBhavaConfidence = bhavaEvents.reduce((highest, event) => Math.max(highest, event.average_confidence ?? 0), 0)
  const bhavaLabel = analysis.bhava.bhava?.dominant_emotion ?? bhavaEvents[0]?.label
  const bhavaConfidence = analysis.bhava.bhava?.confidence ?? highestBhavaConfidence
  const mudraAvailable = hasMudraModelObservation(analysis.mudra)
  const bhavaAvailable = hasBhavaModelObservation(analysis.bhava)
  const technicalAudioAvailable = hasTechnicalAudioEvidence(analysis.audioEvidence)
  return (
    <div className="mx-auto max-w-6xl px-6 py-16 lg:px-10">
      <div className="flex flex-wrap items-end justify-between gap-6"><div><p className="eyebrow mb-3">Step 2 of 3</p><h1 className="text-4xl text-espresso sm:text-5xl">Performance Insight</h1></div><Link to={`/story/${analysisId}`} className="btn-primary"><BookOpen className="h-4 w-4" aria-hidden="true" />View Story</Link></div>
      <div className="mt-10"><AnalysisOverview analysis={analysis} /></div>
      <EvidenceStatus analysis={analysis} />
      <EvidenceProvenancePanel analysis={analysis} />
      <EvidenceProvenanceTimeline analysis={analysis} />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['Facial-expression label', bhavaLabel ?? 'Unavailable', bhavaConfidence ? formatPercent(bhavaConfidence) : '—'],
          ['Mudra events', String(analysis.mudra.mudra_events.length), `${uniqueMudras.length} unique mudras · highest ${highestMudraConfidence ? formatPercent(highestMudraConfidence) : '—'}`],
          ['Pose', 'Not available', 'Current pipeline'],
          ['Audio', 'Not available', 'Current pipeline'],
        ].map(([label, value, detail]) => {
          const isAudio = label === 'Audio'
          const isPose = label === 'Pose'
          const isBhava = label === 'Facial-expression label'
          const isMudra = label === 'Mudra events'
          const displayLabel = isBhava ? 'Facial-expression observation' : isMudra ? 'Mudra observations' : isPose ? 'Pose evidence' : isAudio ? 'Audio evidence' : label
          const displayValue = isPose ? 'Unavailable' : isAudio ? (technicalAudioAvailable ? 'Available' : 'Unavailable') : isBhava ? (bhavaAvailable ? value : 'Unavailable') : isMudra ? (mudraAvailable ? value : 'Unavailable') : value
          const displayDetail = isBhava
            ? bhavaAvailable ? (bhavaConfidence ? `Model output: ${formatPercent(bhavaConfidence)}` : 'Model output available') : 'No model output'
            : isMudra ? (mudraAvailable ? `${uniqueMudras.length} recognized labels; model outputs` : 'No model output')
              : isPose ? 'No usable pose evidence in the production pipeline'
                : isAudio ? (technicalAudioAvailable ? 'technical_only; not narrative evidence' : analysis.audioEvidence?.availability.reason ?? 'No usable technical audio artifact')
                  : detail
          return <div key={label} className="card-surface p-5"><p className="eyebrow">{displayLabel}</p><p className="mt-2 font-display text-xl text-espresso">{displayValue}</p><p className="mt-1 text-xs text-espresso-faint">{displayDetail}</p></div>
        })}
      </div>

      <div className="mt-16">
        <SectionHeading eyebrow="Facial-expression model observation" title="Dominant predicted emotion label" description="This raw model label is not a classical Bhava or Rasa classification, verified emotion, performer intent, or narrative meaning. Reliability warnings remain visible when the prediction distribution is repetitive." />
        <div className="mt-8 card-surface p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3"><p className="font-display text-2xl text-espresso">{bhavaLabel ?? 'Unavailable'}</p><p className="text-sm text-espresso-light">{bhavaConfidence ? formatPercent(bhavaConfidence) : '—'}</p></div>
          {bhavaEvents.length === 1 ? <p className="mt-2 text-sm text-espresso-faint">Duration: {formatDuration(bhavaEvents[0].start_timestamp)}–{formatDuration(bhavaEvents[0].end_timestamp)}</p> : bhavaEvents.length > 1 ? <div className="mt-4 space-y-2">{bhavaEvents.map((event) => <p key={`${event.first_frame_number}-${event.last_frame_number}`} className="text-sm text-espresso-faint">{formatDuration(event.start_timestamp)}–{formatDuration(event.end_timestamp)} · {event.label} · {formatPercent(event.average_confidence)}</p>)}</div> : <p className="mt-2 text-sm text-espresso-faint">No facial-expression observations available.</p>}
        </div>
      </div>
      
      {/* Frame-level analysis section */}
      {frameLevelAnalysis && !loadingFrames && !frameError && (
        <div className="mt-16">
          <SectionHeading 
            eyebrow="Frame analysis" 
            title="Meaningful Mudra Events" 
            description="Time-specific events from the backend analysis. Each card uses its actual representative frame."
          />
          {(frameLevelAnalysis.warnings?.mudra || frameLevelAnalysis.warnings?.bhava) && (
            <div className="mt-6 border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-medium">Model quality warning</p>
              <p className="mt-1">These warnings describe the current model output and do not change any prediction.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {[frameLevelAnalysis.warnings.mudra, frameLevelAnalysis.warnings.bhava]
                  .filter(Boolean)
                  .map((warning) => warning && (
                    <div key={warning.type + warning.dominant_label}>
                      <p className="font-medium">{warning.dominant_label}: {warning.dominant_frames} / {warning.total_frames} frames</p>
                      <p>{warning.message}</p>
                    </div>
                  ))}
              </div>
            </div>
          )}
          {frameLevelAnalysis.occurrences && (
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {Object.entries(frameLevelAnalysis.occurrences).map(([modality, counts]) => (
                <div key={modality} className="border border-line bg-card-surface p-4">
                  <p className="eyebrow">{modality} occurrences</p>
                  <div className="mt-2 space-y-1 text-sm text-espresso">
                    {Object.entries(counts).map(([label, count]) => (
                      <p key={label} className="flex justify-between gap-4"><span>{label}</span><span>{count} frames</span></p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-8">
            <FrameTimeline 
              videoId={analysisId}
              frames={frameLevelAnalysis.frames}
              events={frameLevelAnalysis.events}
              eventModalities={['mudra']}
              onFrameSelect={setSelectedFrame}
            />
          </div>
        </div>
      )}
      {loadingFrames && (
        <div className="mt-16">
          <SectionHeading eyebrow="Frame analysis" title="Frame-level predictions" />
          <div className="mt-8">
            <LoadingState label="Loading frame-level predictions…" />
          </div>
        </div>
      )}
      {frameError && (
        <div className="mt-16">
          <SectionHeading eyebrow="Frame analysis" title="Frame-level predictions" />
          <div className="mt-8">
            <p className="text-sm text-espresso-faint">Frame-level predictions are not available: {frameError.message}</p>
          </div>
        </div>
      )}

      <div className="mt-16"><SectionHeading eyebrow="Fusion" title="Temporal relationship" description="Fusion is represented by the meaningful Mudra events above; facial-expression labels are shown as separate observations." /><div className="mt-6 border border-line bg-card-surface p-5 text-sm text-espresso-light">No additional semantic relationship is inferred beyond timestamp alignment.</div></div>
      <div className="mt-16"><SectionHeading eyebrow="Evidence" title="Unique supporting evidence" description="One entry per unique supporting fact. Event occurrences remain available above." /><div className="mt-8"><EvidencePanel evidence={evidence} /></div></div>
      <NarrativeEvidenceReview analysisId={analysisId} />
      <div className="mt-16"><SectionHeading eyebrow="Analysis evidence" title="Evidence boundaries" /><div className="mt-6 border border-line bg-card-surface p-5 text-sm text-espresso-light"><p>This analysis reports {evidence.grounded.length} curated knowledge reference{evidence.grounded.length === 1 ? '' : 's'}, {evidence.detected.length} detected model observation{evidence.detected.length === 1 ? '' : 's'}, and {evidence.unresolved.length} unresolved observation{evidence.unresolved.length === 1 ? '' : 's'}.</p><p className="mt-2">Model labels and reference information are not promoted into narrative claims. Unresolved observations are not guessed.</p></div></div>

      {/* Frame detail panel */}
      <FrameDetailPanel 
        videoId={analysisId}
        frame={selectedFrame}
        onClose={() => setSelectedFrame(null)}
      />
    </div>
  )
}
