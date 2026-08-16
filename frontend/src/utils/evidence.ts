import type { AnalysisResult, Evidence, EvidenceItem } from '@/types/analysis'

/**
 * If the backend already sends a structured `evidence` object, use it as-is.
 * Otherwise, derive a best-effort evidence breakdown from the individual
 * mudra / bhava / pose / audio fields that are present. This function never
 * invents meanings or statuses — it only reorganizes what the backend sent.
 */
export function deriveEvidence(result?: AnalysisResult | null): Evidence {
  if (!result) {
    return { grounded: [], detected: [], unresolved: [], interpreted: [] }
  }

  if (result.evidence) {
    return result.evidence
  }

  const grounded: EvidenceItem[] = []
  const detected: EvidenceItem[] = []
  const unresolved: EvidenceItem[] = []
  const interpreted: EvidenceItem[] = []

  result.mudra?.detections?.forEach((mudra) => {
    const item: EvidenceItem = {
      id: `mudra-${mudra.name}`,
      label: mudra.name,
      category: mudra.grounded ? 'grounded' : 'unresolved',
      detail: mudra.grounded ? mudra.meaning ?? undefined : 'Meaning unavailable in current knowledge base',
      confidence: mudra.confidence,
    }
    ;(mudra.grounded ? grounded : unresolved).push(item)
  })

  if (result.bhava?.dominant_emotion) {
    detected.push({
      id: 'bhava-dominant',
      label: `${result.bhava.dominant_emotion} bhava detected`,
      category: 'detected',
      confidence: result.bhava.confidence ?? result.bhava.bhava_confidence,
    })
  }

  if (result.pose?.primary_pose) {
    detected.push({
      id: 'pose-primary',
      label: `${result.pose.primary_pose} pose detected`,
      category: 'detected',
      confidence: result.pose.confidence ?? result.pose.pose_confidence,
    })
  }

  if (result.audio?.audio_type) {
    const isRhythmicOnly = result.audio.audio_type === 'rhythmic-only'
    ;(isRhythmicOnly ? unresolved : detected).push({
      id: 'audio-type',
      label: isRhythmicOnly ? 'Audio classified as rhythmic-only' : `Audio classified as ${result.audio.audio_type}`,
      category: isRhythmicOnly ? 'unresolved' : 'detected',
      detail: isRhythmicOnly ? 'Meaningful lyric evidence unavailable.' : undefined,
      confidence: result.audio.audio_confidence,
    })
  }

  return { grounded, detected, unresolved, interpreted }
}

export function evidenceCount(evidence: Evidence): number {
  return (
    evidence.grounded.length +
    evidence.detected.length +
    evidence.unresolved.length +
    evidence.interpreted.length
  )
}
