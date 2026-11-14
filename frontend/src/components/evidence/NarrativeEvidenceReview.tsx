import { useEffect, useState, type FormEvent } from 'react'
import { AlertCircle, Check, Send, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ApiErrorPayload } from '@/types/analysis'
import {
  getNarrativeEvidenceReview, prepareNarrativeEvidenceCandidates, reviewNarrativeEvidence, submitNarrativeEvidence,
  submitNarrativeEvidenceForReview, type NarrativeEvidenceReview, type NarrativeEvidenceStatus,
  updateNarrativeEvidenceDraft,
} from '@/services/api'

const statusStyle: Record<NarrativeEvidenceStatus, string> = {
  draft: 'bg-stone-100 text-stone-700', submitted: 'bg-amber-100 text-amber-900',
  verified: 'bg-emerald-100 text-emerald-900', rejected: 'bg-rose-100 text-rose-900',
}
const emptyDecision = { reviewer: '', method: '', confidence: '1', reason: '', eligible: false }

export default function NarrativeEvidenceReview({ analysisId }: { analysisId: string }) {
  const [review, setReview] = useState<NarrativeEvidenceReview | null>(null)
  const [error, setError] = useState<ApiErrorPayload | null>(null)
  const [sending, setSending] = useState(false)
  const [decision, setDecision] = useState(emptyDecision)
  const [editing, setEditing] = useState<Record<string, { statement: string; performance_mode: 'pure_dance' | 'narrative_dance' | 'unknown' }>>({})
  const [form, setForm] = useState({ statement: '', sourceReference: '', submittedBy: '', method: '', confidence: '0.9', startTime: '', endTime: '', mode: 'narrative_dance', status: 'submitted' as 'draft' | 'submitted' })

  const load = async () => {
    try { setError(null); setReview(await getNarrativeEvidenceReview(analysisId)) } catch (err) {
      const apiError = err as ApiErrorPayload
      if (apiError.status !== 404) setError(apiError)
      else setReview({ analysis_id: analysisId, video_id: analysisId, records: [], story_eligible: false, story_eligibility_reason: 'No verified, production-eligible evidence is available.' })
    }
  }
  useEffect(() => { void load() }, [analysisId])

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSending(true); setError(null)
    const span = form.startTime === '' && form.endTime === '' ? null : { start_time: Number(form.startTime), end_time: Number(form.endTime) }
    try {
      await submitNarrativeEvidence(analysisId, {
        analysis_id: analysisId, video_id: analysisId, statement: form.statement, statement_type: 'verified_narrative_event', source_reference: form.sourceReference,
        submitted_by: form.submittedBy, verification_method: form.method, verification_confidence: Number(form.confidence), span,
        provenance: { type: 'curated_annotation', reference: form.sourceReference }, performance_mode: form.mode as 'pure_dance' | 'narrative_dance', status: form.status,
      })
      setForm({ ...form, statement: '', sourceReference: '', startTime: '', endTime: '' }); await load()
    } catch (err) { setError(err as ApiErrorPayload) } finally { setSending(false) }
  }
  const submitDraft = async (id: string) => { setSending(true); setError(null); try { await submitNarrativeEvidenceForReview(analysisId, id); await load() } catch (err) { setError(err as ApiErrorPayload) } finally { setSending(false) } }
  const prepareCandidates = async () => { setSending(true); setError(null); try { await prepareNarrativeEvidenceCandidates(analysisId); await load() } catch (err) { setError(err as ApiErrorPayload) } finally { setSending(false) } }
  const saveDraft = async (id: string, fallback: { statement: string; performance_mode: 'pure_dance' | 'narrative_dance' | 'unknown' }) => { setSending(true); setError(null); try { await updateNarrativeEvidenceDraft(analysisId, id, editing[id] ?? fallback); setEditing((current) => { const next = { ...current }; delete next[id]; return next }); await load() } catch (err) { setError(err as ApiErrorPayload) } finally { setSending(false) } }
  const decide = async (id: string, status: 'verified' | 'rejected') => {
    setSending(true); setError(null)
    try {
      await reviewNarrativeEvidence(analysisId, id, { status, verified_by: decision.reviewer, verification_method: decision.method, verification_confidence: Number(decision.confidence), production_eligible: status === 'verified' && decision.eligible, review_reason: decision.reason })
      setDecision(emptyDecision); await load()
    } catch (err) { setError(err as ApiErrorPayload) } finally { setSending(false) }
  }

  return <section className="mt-16" aria-labelledby="narrative-evidence-heading">
    <p className="eyebrow">Narrative evidence review</p>
    <div className="mt-4 border border-line bg-card-surface p-6">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 id="narrative-evidence-heading" className="font-display text-2xl text-espresso">Curated narrative evidence</h2><p className="mt-1 text-sm text-espresso-light">Analysis ID: <span className="font-mono text-xs">{analysisId}</span></p></div><p className={`px-2 py-1 text-xs font-medium ${review?.story_eligible ? 'bg-emerald-100 text-emerald-900' : 'bg-stone-100 text-stone-700'}`}>Story eligible: {review?.story_eligible ? 'Yes' : 'No'}</p></div>
      <p className="mt-3 text-sm text-espresso-faint">{review?.story_eligibility_reason ?? 'Loading review status...'}</p>
      {review?.story_eligible && <Link to={`/story/${analysisId}`} className="mt-3 inline-flex text-sm font-medium text-espresso underline underline-offset-4">Open validated Story generation</Link>}
      <p className="mt-3 border-l-2 border-amber-500 pl-3 text-xs leading-relaxed text-espresso-light">AI/model observations shown elsewhere on this page are not narrative evidence and cannot be approved here. Add only a source-backed curator statement, then record an explicit reviewer decision.</p>
      {error && <p className="mt-4 flex items-center gap-2 text-sm text-rose-700"><AlertCircle className="h-4 w-4" />{error.message}</p>}
      {review?.records.length === 0 && <div className="mt-5 border border-line bg-parchment/40 p-4"><p className="text-sm text-espresso">No narrative evidence has been prepared yet.</p><p className="mt-1 text-xs text-espresso-light">Preparation creates AI-assisted drafts from the persisted completed-analysis summary. They cannot generate a Story until a human edits, submits, verifies, and marks them eligible.</p><button type="button" disabled={sending} onClick={() => void prepareCandidates()} className="btn-secondary mt-3 text-sm">Prepare Evidence Candidates</button></div>}
      <form onSubmit={submit} className="mt-6 grid gap-4 border-t border-line pt-6 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm text-espresso">Source-backed narrative statement<textarea required value={form.statement} onChange={(e) => setForm({ ...form, statement: e.target.value })} className="mt-1 min-h-24 w-full border border-line bg-white px-3 py-2" /></label>
        <label className="text-sm text-espresso">Source reference<input required value={form.sourceReference} onChange={(e) => setForm({ ...form, sourceReference: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Submitted by<input required value={form.submittedBy} onChange={(e) => setForm({ ...form, submittedBy: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label>
        <label className="text-sm text-espresso">Evidence method<input required value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Evidence confidence<input required min="0" max="1" step="0.01" type="number" value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label>
        <label className="text-sm text-espresso">Start time (seconds)<input min="0" step="0.1" type="number" value={form.startTime} onChange={(e) => setForm({ ...form, startTime: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">End time (seconds)<input min="0" step="0.1" type="number" value={form.endTime} onChange={(e) => setForm({ ...form, endTime: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label>
        <label className="text-sm text-espresso">Performance mode<select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2"><option value="narrative_dance">Narrative dance</option><option value="pure_dance">Pure dance</option></select></label><label className="text-sm text-espresso">Lifecycle state<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as 'draft' | 'submitted' })} className="mt-1 w-full border border-line bg-white px-3 py-2"><option value="draft">Draft</option><option value="submitted">Submit for review</option></select></label>
        <div className="sm:col-span-2 flex justify-end"><button disabled={sending} className="btn-primary" type="submit"><Send className="h-4 w-4" />{sending ? 'Saving...' : 'Save evidence'}</button></div>
      </form>
      {review && review.records.length > 0 && <div className="mt-6 border-t border-line pt-5"><h3 className="text-sm font-medium text-espresso">Persisted evidence lifecycle</h3><div className="mt-3 space-y-3">{review.records.map((record) => <div className="border border-line p-4" key={record.evidence_id}><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-espresso">{record.statement}</p><span className={`px-2 py-1 text-xs font-medium ${statusStyle[record.status]}`}>{record.status}</span></div><p className="mt-1 text-xs text-espresso-faint">Source: {record.source_reference}{record.verified_by ? ` | Reviewed by: ${record.verified_by}` : ''}</p>{record.candidate_origin === 'ai_assisted' && <p className="mt-2 text-xs font-medium text-amber-800">AI-assisted draft — requires human verification</p>}
        {record.status === 'draft' && <div className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2"><label className="sm:col-span-2 text-sm text-espresso">Narrative statement<textarea value={editing[record.evidence_id]?.statement ?? record.statement} onChange={(e) => setEditing({ ...editing, [record.evidence_id]: { statement: e.target.value, performance_mode: editing[record.evidence_id]?.performance_mode ?? record.performance_mode } })} className="mt-1 min-h-20 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Performance mode<select value={editing[record.evidence_id]?.performance_mode ?? record.performance_mode} onChange={(e) => setEditing({ ...editing, [record.evidence_id]: { statement: editing[record.evidence_id]?.statement ?? record.statement, performance_mode: e.target.value as 'pure_dance' | 'narrative_dance' | 'unknown' } })} className="mt-1 w-full border border-line bg-white px-3 py-2"><option value="unknown">Choose before submitting</option><option value="narrative_dance">Narrative dance</option><option value="pure_dance">Pure dance</option></select></label><div className="flex items-end gap-3"><button type="button" disabled={sending} onClick={() => void saveDraft(record.evidence_id, { statement: record.statement, performance_mode: record.performance_mode })} className="btn-secondary text-sm">Save draft</button><button type="button" disabled={sending || (editing[record.evidence_id]?.performance_mode ?? record.performance_mode) === 'unknown'} onClick={() => void submitDraft(record.evidence_id)} className="btn-primary text-sm">Submit for reviewer decision</button></div></div>}
        {record.status === 'submitted' && <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2"><label className="text-sm text-espresso">Reviewer identity<input required value={decision.reviewer} onChange={(e) => setDecision({ ...decision, reviewer: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Review method<input required value={decision.method} onChange={(e) => setDecision({ ...decision, method: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Review confidence<input required min="0" max="1" step="0.01" type="number" value={decision.confidence} onChange={(e) => setDecision({ ...decision, confidence: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="text-sm text-espresso">Review reason<input required value={decision.reason} onChange={(e) => setDecision({ ...decision, reason: e.target.value })} className="mt-1 w-full border border-line bg-white px-3 py-2" /></label><label className="sm:col-span-2 flex items-center gap-2 text-sm text-espresso"><input type="checkbox" checked={decision.eligible} onChange={(e) => setDecision({ ...decision, eligible: e.target.checked })} />Mark verified evidence production eligible</label><div className="sm:col-span-2 flex flex-wrap gap-3"><button type="button" disabled={sending} onClick={() => void decide(record.evidence_id, 'verified')} className="btn-primary text-sm"><Check className="h-4 w-4" />Verify evidence</button><button type="button" disabled={sending} onClick={() => void decide(record.evidence_id, 'rejected')} className="btn-secondary text-sm"><X className="h-4 w-4" />Reject evidence</button></div></div>}
      </div>)}</div></div>}
    </div>
  </section>
}
