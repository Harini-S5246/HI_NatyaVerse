import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight, Check, Download, Music2, Upload } from 'lucide-react'
import LoadingState from '@/components/common/LoadingState'
import { API_BASE_URL } from '@/services/api'
import type { SupportedLanguage } from '@/types/analysis'
import SceneVisualReferences from '@/components/storyToDance/SceneVisualReferences'
import {
  getStoryToDanceWorkflow,
  generateStoryToDanceWorkflow,
  getStoryToDanceStory,
  generateStoryToDancePlan,
  generateStoryToDancePerformance,
  getStoryToDanceVisualReferences,
} from '@/services/storyToDanceApi'
import type {
  DancePlan,
  DanceScene,
  DanceGenerationResult,
  MovementIntent,
  SceneVisualReferenceRequest,
  SceneVisualReferences as SceneVisualReferencesResult,
  StoryToDanceRecord,
} from '@/types/storyToDance'

interface CreateDanceProps {
  language: SupportedLanguage
}

const LANGUAGE_CODES: Record<SupportedLanguage, string> = {
  English: 'en',
  Tamil: 'ta',
  Hindi: 'hi',
  Malayalam: 'ml',
  Telugu: 'te',
  Kannada: 'kn',
  Bengali: 'bn',
}

function selectMappedMudraLabel(mudras: DanceScene['dance_mapping']['mudras']): string | null {
  const mapped = mudras.filter((mapping) => mapping.status === 'mapped' && mapping.mudra)
  const explicit = mapped.find((mapping) => (
    mapping.mudra
    && new RegExp(
      `(^|[^\\p{L}\\p{N}])${mapping.mudra.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^\\p{L}\\p{N}]|$)`,
      'iu',
    ).test(mapping.concept)
  ))
  return explicit?.mudra ?? mapped[0]?.mudra ?? null
}

function sceneVisualReferenceRequest(scene: DanceScene): SceneVisualReferenceRequest {
  const supportedConcept = scene.bharatanatyam_concept.find(
    (item) => item.mapping_status === 'supported_concept',
  )
  const supportedBhava = scene.dance_mapping.bhava.find((item) => item.bhava)
  return {
    scene_id: scene.scene_id,
    mudra_label: selectMappedMudraLabel(scene.dance_mapping.mudras),
    bhava_label: supportedBhava?.bhava ?? null,
    pose_label: supportedConcept?.concept ?? null,
  }
}

const COPY: Record<SupportedLanguage, {
  eyebrow: string
  title: string
  intro: string
  paste: string
  titleLabel: string
  file: string
  generate: string
  understanding: string
  summary: string
  scenes: string
  characters: string
  action: string
  objects: string
  place: string
  expression: string
  interpretation: string
  mudra: string
  bhava: string
  movement: string
  choreography: string
  poseSequence: string
  performance: string
  generateDance: string
  mappingUnavailable: string
}> = {
  English: {
    eyebrow: 'Story → Bharatanatyam',
    title: 'Create a Dance Plan',
    intro: 'Bring a story. HI-Natya Verse will extract its scenes and map only what the available Bharatanatyam knowledge supports.',
    paste: 'Paste or write a story',
    titleLabel: 'Story title (optional)',
    file: 'Choose a .txt or .md story file',
    generate: 'Generate Dance Plan',
    understanding: 'Story understanding',
    summary: 'Source-grounded summary',
    scenes: 'Scenes',
    characters: 'Characters',
    action: 'Action',
    objects: 'Objects',
    place: 'Location',
    expression: 'Expressions from source',
    interpretation: 'Bharatanatyam interpretation',
    mudra: 'Mudra',
    bhava: 'Bhava / Abhinaya',
    movement: 'Movement / Adavu',
    choreography: 'Ordered choreography plan',
    poseSequence: 'Pose sequence',
    performance: 'Generated Dance',
    generateDance: 'Generate Dance',
    mappingUnavailable: 'Mapping unavailable — review required',
  },
  Tamil: {
    eyebrow: 'கதை → பரதநாட்டியம்',
    title: 'நடனத் திட்டத்தை உருவாக்கு',
    intro: 'கதையை வழங்குங்கள். கிடைக்கும் பரதநாட்டிய அறிவு ஆதரிக்கும் அம்சங்களை மட்டுமே அமைப்பு வரைபடமாக்கும்.',
    paste: 'கதையை எழுதவும் அல்லது ஒட்டவும்',
    titleLabel: 'கதைத் தலைப்பு (விருப்பம்)',
    file: '.txt அல்லது .md கதைக் கோப்பைத் தேர்ந்தெடுக்கவும்',
    generate: 'நடனத் திட்டத்தை உருவாக்கு',
    understanding: 'கதைப் புரிதல்',
    summary: 'மூலக் கதையை அடிப்படையாகக் கொண்ட சுருக்கம்',
    scenes: 'காட்சிகள்',
    characters: 'பாத்திரங்கள்',
    action: 'செயல்',
    objects: 'பொருட்கள்',
    place: 'இடம்',
    expression: 'மூலத்தில் உள்ள உணர்வுகள்',
    interpretation: 'பரதநாட்டிய விளக்கம்',
    mudra: 'முத்திரை',
    bhava: 'பாவம் / அபிநயம்',
    movement: 'இயக்கம் / அடவு',
    choreography: 'வரிசைப்படுத்தப்பட்ட நடனத் திட்டம்',
    poseSequence: 'உடல் நிலை வரிசை',
    performance: 'உருவாக்கப்பட்ட நடனக் காட்சிப்படுத்தல்',
    generateDance: 'நடனத்தை உருவாக்கு',
    mappingUnavailable: 'வரைபடம் இல்லை — மதிப்பாய்வு தேவை',
  },
  Hindi: {
    eyebrow: 'कहानी → भरतनाट्यम',
    title: 'नृत्य योजना बनाएँ',
    intro: 'कहानी दें। HI-Natya Verse उसके दृश्य निकालेगा और केवल उपलब्ध भरतनाट्यम ज्ञान से समर्थित तत्वों का मानचित्रण करेगा।',
    paste: 'कहानी लिखें या चिपकाएँ',
    titleLabel: 'कहानी का शीर्षक (वैकल्पिक)',
    file: '.txt या .md कहानी फ़ाइल चुनें',
    generate: 'नृत्य योजना बनाएँ',
    understanding: 'कहानी की समझ',
    summary: 'स्रोत-आधारित सारांश',
    scenes: 'दृश्य',
    characters: 'पात्र',
    action: 'क्रिया',
    objects: 'वस्तुएँ',
    place: 'स्थान',
    expression: 'स्रोत में व्यक्त भाव',
    interpretation: 'भरतनाट्यम व्याख्या',
    mudra: 'मुद्रा',
    bhava: 'भाव / अभिनय',
    movement: 'गति / अडवु',
    choreography: 'क्रमबद्ध नृत्य योजना',
    poseSequence: 'मुद्रा क्रम',
    performance: 'निर्मित नृत्य दृश्यांकन',
    generateDance: 'नृत्य बनाएँ',
    mappingUnavailable: 'मानचित्रण उपलब्ध नहीं — समीक्षा आवश्यक',
  },
  Malayalam: {
    eyebrow: 'കഥ → ഭരതനാട്യം',
    title: 'നൃത്ത പദ്ധതി സൃഷ്ടിക്കുക',
    intro: 'കഥ നൽകുക. ലഭ്യമായ ഭരതനാട്യ അറിവ് പിന്തുണയ്ക്കുന്ന ഘടകങ്ങൾ മാത്രം HI-Natya Verse മാപ്പ് ചെയ്യും.',
    paste: 'കഥ എഴുതുക അല്ലെങ്കിൽ ഒട്ടിക്കുക',
    titleLabel: 'കഥയുടെ പേര് (ഐച്ഛികം)',
    file: '.txt അല്ലെങ്കിൽ .md കഥാ ഫയൽ തിരഞ്ഞെടുക്കുക',
    generate: 'നൃത്ത പദ്ധതി സൃഷ്ടിക്കുക',
    understanding: 'കഥയുടെ ഘടന',
    summary: 'ഉറവിടത്തെ അടിസ്ഥാനമാക്കിയ സംഗ്രഹം',
    scenes: 'രംഗങ്ങൾ',
    characters: 'കഥാപാത്രങ്ങൾ',
    action: 'പ്രവർത്തനം',
    objects: 'വസ്തുക്കൾ',
    place: 'സ്ഥലം',
    expression: 'ഉറവിടത്തിലെ വികാരങ്ങൾ',
    interpretation: 'ഭരതനാട്യ വ്യാഖ്യാനം',
    mudra: 'മുദ്ര',
    bhava: 'ഭാവം / അഭിനയം',
    movement: 'ചലനം / അടവ്',
    choreography: 'ക്രമപ്പെടുത്തിയ നൃത്ത പദ്ധതി',
    poseSequence: 'പോസ് ക്രമം',
    performance: 'സൃഷ്ടിച്ച നൃത്ത ദൃശ്യാവിഷ്കാരം',
    generateDance: 'നൃത്തം സൃഷ്ടിക്കുക',
    mappingUnavailable: 'മാപ്പിംഗ് ലഭ്യമല്ല — അവലോകനം ആവശ്യമാണ്',
  },
  Telugu: {
    eyebrow: 'కథ → భరతనాట్యం',
    title: 'నృత్య ప్రణాళికను సృష్టించండి',
    intro: 'కథను అందించండి. అందుబాటులో ఉన్న భరతనాట్య జ్ఞానం మద్దతిచ్చే అంశాలనే HI-Natya Verse మ్యాప్ చేస్తుంది.',
    paste: 'కథను వ్రాయండి లేదా అతికించండి',
    titleLabel: 'కథ శీర్షిక (ఐచ్ఛికం)',
    file: '.txt లేదా .md కథ ఫైల్‌ను ఎంచుకోండి',
    generate: 'నృత్య ప్రణాళికను సృష్టించండి',
    understanding: 'కథ అవగాహన',
    summary: 'మూలాధారిత సారాంశం',
    scenes: 'దృశ్యాలు',
    characters: 'పాత్రలు',
    action: 'చర్య',
    objects: 'వస్తువులు',
    place: 'స్థలం',
    expression: 'మూలంలోని భావాలు',
    interpretation: 'భరతనాట్య వివరణ',
    mudra: 'ముద్ర',
    bhava: 'భావం / అభినయం',
    movement: 'కదలిక / అడవు',
    choreography: 'క్రమబద్ధమైన నృత్య ప్రణాళిక',
    poseSequence: 'భంగిమల క్రమం',
    performance: 'సృష్టించిన నృత్య దృశ్యാവിഷ్కరణ',
    generateDance: 'నృత్యాన్ని సృష్టించండి',
    mappingUnavailable: 'మ్యాపింగ్ అందుబాటులో లేదు — సమీక్ష అవసరం',
  },
  Kannada: {
    eyebrow: 'ಕಥೆ → ಭರತನಾಟ್ಯ',
    title: 'ನೃತ್ಯ ಯೋಜನೆ ರಚಿಸಿ',
    intro: 'ಕಥೆಯನ್ನು ನೀಡಿ. ಲಭ್ಯವಿರುವ ಭರತನಾಟ್ಯ ಜ್ಞಾನ ಬೆಂಬಲಿಸುವ ಅಂಶಗಳನ್ನು ಮಾತ್ರ HI-Natya Verse ಮ್ಯಾಪ್ ಮಾಡುತ್ತದೆ.',
    paste: 'ಕಥೆಯನ್ನು ಬರೆಯಿರಿ ಅಥವಾ ಅಂಟಿಸಿ',
    titleLabel: 'ಕಥೆಯ ಶೀರ್ಷಿಕೆ (ಐಚ್ಛಿಕ)',
    file: '.txt ಅಥವಾ .md ಕಥೆ ಕಡತವನ್ನು ಆಯ್ಕೆಮಾಡಿ',
    generate: 'ನೃತ್ಯ ಯೋಜನೆ ರಚಿಸಿ',
    understanding: 'ಕಥೆಯ ಅರಿವು',
    summary: 'ಮೂಲಾಧಾರಿತ ಸಾರಾಂಶ',
    scenes: 'ದೃಶ್ಯಗಳು',
    characters: 'ಪಾತ್ರಗಳು',
    action: 'ಕ್ರಿಯೆ',
    objects: 'ವಸ್ತುಗಳು',
    place: 'ಸ್ಥಳ',
    expression: 'ಮೂಲದಲ್ಲಿರುವ ಭಾವಗಳು',
    interpretation: 'ಭರತನಾಟ್ಯ ವ್ಯಾಖ್ಯಾನ',
    mudra: 'ಮುದ್ರೆ',
    bhava: 'ಭಾವ / ಅಭಿನಯ',
    movement: 'ಚಲನೆ / ಅಡವು',
    choreography: 'ಕ್ರಮಬದ್ಧ ನೃತ್ಯ ಯೋಜನೆ',
    poseSequence: 'ಭಂಗಿ ಅನುಕ್ರಮ',
    performance: 'ರಚಿಸಿದ ನೃತ್ಯ ದೃಶ್ಯೀಕರಣ',
    generateDance: 'ನೃತ್ಯ ರಚಿಸಿ',
    mappingUnavailable: 'ಮ್ಯಾಪಿಂಗ್ ಲಭ್ಯವಿಲ್ಲ — ಪರಿಶೀಲನೆ ಅಗತ್ಯ',
  },
  Bengali: {
    eyebrow: 'গল্প → ভরতনাট্যম',
    title: 'নৃত্য পরিকল্পনা তৈরি করুন',
    intro: 'গল্প দিন। উপলভ্য ভরতনাট্যম জ্ঞান যতটুকু সমর্থন করে, HI-Natya Verse শুধু ততটুকুই মানচিত্র করবে।',
    paste: 'গল্প লিখুন বা পেস্ট করুন',
    titleLabel: 'গল্পের শিরোনাম (ঐচ্ছিক)',
    file: '.txt বা .md গল্পের ফাইল নির্বাচন করুন',
    generate: 'নৃত্য পরিকল্পনা তৈরি করুন',
    understanding: 'গল্পের উপলব্ধি',
    summary: 'উৎস-ভিত্তিক সারাংশ',
    scenes: 'দৃশ্য',
    characters: 'চরিত্র',
    action: 'কাজ',
    objects: 'বস্তু',
    place: 'স্থান',
    expression: 'উৎসে প্রকাশিত অনুভূতি',
    interpretation: 'ভরতনাট্যম ব্যাখ্যা',
    mudra: 'মুদ্রা',
    bhava: 'ভাব / অভিনয়',
    movement: 'চলন / আদভু',
    choreography: 'ক্রমবদ্ধ নৃত্য পরিকল্পনা',
    poseSequence: 'ভঙ্গির ক্রম',
    performance: 'তৈরি নৃত্য দৃশ্যায়ন',
    generateDance: 'নৃত্য তৈরি করুন',
    mappingUnavailable: 'ম্যাপিং অনুপলভ্য — পর্যালোচনা প্রয়োজন',
  },
}

function languageName(language: string): string {
  return language.toUpperCase()
}

function getGeneratedVideoUrl(generation: DanceGenerationResult): string | null {
  if (generation.status !== 'completed' || !generation.video_url || !generation.generation_id) {
    return null
  }

  const normalizedVideoUrl = generation.video_url.trim()
  const expectedPath = [
    '/api/story-to-dance/stories',
    encodeURIComponent(generation.story_id),
    'plans',
    encodeURIComponent(generation.dance_plan_id),
    'choreographies',
    encodeURIComponent(generation.choreography_id),
    'generations',
    encodeURIComponent(generation.generation_id),
    'video',
  ].join('/')
  const expectedUrl = new URL(expectedPath, API_BASE_URL)

  try {
    const resolvedUrl = new URL(normalizedVideoUrl, API_BASE_URL)
    if (resolvedUrl.pathname === expectedUrl.pathname) {
      expectedUrl.searchParams.set('generation_id', generation.generation_id)
      return expectedUrl.toString()
    }
  } catch {
    return null
  }

  if (normalizedVideoUrl.startsWith('/')) {
    const fallback = new URL(normalizedVideoUrl, API_BASE_URL)
    fallback.searchParams.set('generation_id', generation.generation_id)
    return fallback.toString()
  }

  return expectedUrl.toString()
}

function MovementDetails({ intent }: { intent: MovementIntent | null }) {
  if (!intent) {
    return <p className="text-unresolved">No source-grounded movement mapping is currently available.</p>
  }

  const sourceSupported = intent.mapping_status === 'supported_concept'
  const supportedActions = intent.actions.filter(
    (action) => action.mapping_status === 'supported_concept' && action.movement_concept,
  )
  return (
    <div className="space-y-1">
      <p className="font-medium">Movement Intent</p>
      <p>
        <span className="font-medium">Action:</span>{' '}
        {intent.actions.length > 1
          ? intent.actions.map((action) => action.action).join(' → ')
          : intent.action || '—'}
      </p>
      <p><span className="font-medium">Target:</span> {intent.target || '—'}</p>
      <p>
        <span className="font-medium">Direction:</span>{' '}
        {intent.actions.length > 1
          ? intent.actions.map((action) => action.direction || '—').join(' → ')
          : intent.direction || '—'}
      </p>
      <p className="mt-2 font-medium">Bharatanatyam Movement</p>
      {sourceSupported ? (
        <p>Concept: {intent.movement_concept}</p>
      ) : supportedActions.length > 0 ? (
        <div>
          <p>Source-supported component concepts:</p>
          {supportedActions.map((action) => (
            <p key={`${action.action}-${action.movement_concept}`}>
              {action.action}: {action.movement_concept}
            </p>
          ))}
          <p>Combined sequence: Review required</p>
        </div>
      ) : (
        <p>Review required</p>
      )}
      <p><span className="font-medium">Adavu:</span> {intent.candidate_adavu || 'Not assigned'}</p>
      <p>
        <span className="font-medium">Mapping status:</span>{' '}
        {sourceSupported ? 'Source-supported concept' : 'Review required'}
      </p>
      {!sourceSupported && intent.mapping_reason && supportedActions.length === 0 && (
        <p><span className="font-medium">Reason:</span> {intent.mapping_reason}</p>
      )}
      {(intent.source || supportedActions.some((action) => action.source)) && (
        <p>
          <span className="font-medium">Source:</span> {intent.source}
          {intent.source_reference ? ` — ${intent.source_reference}` : ''}
          {!intent.source && supportedActions.map((action) => (
            <span key={`${action.action}-${action.source_reference}`}>
              {action.source ? ` ${action.source}${action.source_reference ? ` — ${action.source_reference}` : ''}` : ''}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}

export default function CreateDance({ language }: CreateDanceProps) {
  const copy = COPY[language]
  const [searchParams, setSearchParams] = useSearchParams()
  const storyId = searchParams.get('story_id')
  const workflowId = searchParams.get('workflow_id')
  const [storyText, setStoryText] = useState('')
  const [title, setTitle] = useState('')
  const [fileName, setFileName] = useState('')
  const [record, setRecord] = useState<StoryToDanceRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [generationResult, setGenerationResult] = useState<DanceGenerationResult | null>(null)
  const [generationBusy, setGenerationBusy] = useState(false)
  const [visualReferenceState, setVisualReferenceState] = useState<{
    status: 'idle' | 'loading' | 'loaded' | 'error'
    byScene: Record<string, SceneVisualReferencesResult>
    error: string | null
  }>({ status: 'idle', byScene: {}, error: null })
  const [videoPlaybackStatus, setVideoPlaybackStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [videoPlaybackError, setVideoPlaybackError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const planRequestInFlight = useRef(false)
  const plan = record?.story_id === storyId ? record.dance_plan : null
  const currentGeneration = generationResult
    && generationResult.story_id === plan?.story_id
    && generationResult.dance_plan_id === plan?.dance_plan_id
    && generationResult.choreography_id === plan?.choreography_id
    ? generationResult
    : null
  const currentVideoUrl = currentGeneration
    ? getGeneratedVideoUrl(currentGeneration)
    : null

  useEffect(() => {
    if (!plan) {
      setVisualReferenceState({ status: 'idle', byScene: {}, error: null })
      return
    }

    let active = true
    setVisualReferenceState({ status: 'loading', byScene: {}, error: null })
    const requests = plan.scenes.map(sceneVisualReferenceRequest)
    getStoryToDanceVisualReferences(requests)
      .then((references) => {
        if (!active) return
        const byScene = Object.fromEntries(
          references.map((reference) => [reference.scene_id, reference]),
        )
        setVisualReferenceState({ status: 'loaded', byScene, error: null })
      })
      .catch((cause: unknown) => {
        if (active) {
          setVisualReferenceState({
            status: 'error',
            byScene: {},
            error: cause instanceof Error ? cause.message : 'Reference lookup failed.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [plan])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !currentVideoUrl) {
      setVideoPlaybackStatus('idle')
      setVideoPlaybackError(null)
      return
    }

    const reportPlaybackError = () => {
      const error = video.error
      const code = error?.code ?? 0
      const descriptions: Record<number, string> = {
        1: 'playback was aborted',
        2: 'a network error interrupted playback',
        3: 'the browser could not decode the video',
        4: 'the browser does not support this video source',
      }
      setVideoPlaybackStatus('error')
      setVideoPlaybackError(
        `Chrome failed to load this generated video (MediaError ${code}: ${descriptions[code] ?? 'unknown media error'}).`,
      )
    }
    const verifyMetadata = () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) {
        setVideoPlaybackStatus('error')
        setVideoPlaybackError('The browser loaded video metadata but reported an invalid duration.')
        return
      }
      setVideoPlaybackError(null)
      setVideoPlaybackStatus('ready')
    }

    setVideoPlaybackStatus('loading')
    setVideoPlaybackError(null)
    video.addEventListener('loadedmetadata', verifyMetadata)
    video.addEventListener('error', reportPlaybackError)
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) verifyMetadata()
    return () => {
      video.removeEventListener('loadedmetadata', verifyMetadata)
      video.removeEventListener('error', reportPlaybackError)
    }
  }, [currentVideoUrl])

  useEffect(() => {
    if (!storyId) return
    let active = true
    setBusy(true)
    setError(null)
    setRecord(null)
    setGenerationResult(null)
    const loadStory = workflowId
      ? getStoryToDanceWorkflow(workflowId).then((workflow) => {
        if (workflow.story.story_id !== storyId) {
          throw new Error('The saved workflow belongs to a different story.')
        }
        return workflow
      })
      : getStoryToDanceStory(storyId).then((story) => ({ story, generation: null }))
    loadStory
      .then((saved) => {
        if (!active) return
        setRecord(saved.story)
        setStoryText(saved.story.story_text)
        setTitle(saved.story.title)
        if (saved.generation) {
          if (saved.generation.status === 'completed') {
            const videoUrl = getGeneratedVideoUrl(saved.generation)
            if (!videoUrl) {
              throw new Error('The saved completed workflow has no usable video URL.')
            }
            setGenerationResult({ ...saved.generation, video_url: videoUrl })
          } else {
            setGenerationResult(saved.generation)
          }
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'The saved story could not be loaded.')
      })
      .finally(() => {
        if (active) setBusy(false)
      })
    return () => {
      active = false
    }
  }, [storyId, workflowId])

  const updateStoryText = (value: string) => {
    setStoryText(value)
    setFileName('')
    setRecord(null)
    setGenerationResult(null)
    setError(null)
    if (storyId) setSearchParams({}, { replace: true })
  }

  const onFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const supported = /\.(txt|md)$/i.test(file.name)
    if (!supported) {
      setError('Choose a plain-text .txt or Markdown .md story file.')
      event.target.value = ''
      return
    }
    if (file.size > 100_000) {
      setError('Story files must be 100 KB or smaller.')
      event.target.value = ''
      return
    }
    try {
      const text = await file.text()
      updateStoryText(text)
      setTitle(file.name.replace(/\.(txt|md)$/i, ''))
      setFileName(file.name)
      event.target.value = ''
    } catch {
      setError('The selected story file could not be read.')
    }
  }

  const generatePlan = async () => {
    if (!storyText.trim() || busy || planRequestInFlight.current) return
    planRequestInFlight.current = true
    setBusy(true)
    setError(null)
    try {
      const normalizedTitle = title.trim() || 'Untitled Story'
      const languageCode = LANGUAGE_CODES[language]
      const currentRecordMatchesInput = record
        && record.story_text === storyText.trim()
        && record.title === normalizedTitle
        && record.language === languageCode

      if (currentRecordMatchesInput) {
        const planned = await generateStoryToDancePlan(record.story_id)
        if (!planned.dance_plan) {
          throw new Error('The story planner did not return a usable choreography plan.')
        }
        setRecord(planned)
        setSearchParams({ story_id: planned.story_id }, { replace: true })
        setGenerationResult(null)
        await generatePerformance(planned.dance_plan)
      } else {
        const workflowId = crypto.randomUUID()
        const workflow = await generateStoryToDanceWorkflow(
          storyText.trim(),
          languageCode,
          workflowId,
          title.trim() || undefined,
        )
        const generatedPlan = workflow.story.dance_plan
        if (!generatedPlan) {
          throw new Error('The workflow completed without returning its choreography plan.')
        }
        setRecord(workflow.story)
        setSearchParams(
          { story_id: workflow.story.story_id, workflow_id: workflowId },
          { replace: true },
        )
        if (workflow.generation.status === 'completed') {
          const videoUrl = getGeneratedVideoUrl(workflow.generation)
          if (!videoUrl) {
            throw new Error('The completed generation did not include a usable video URL.')
          }
          setGenerationResult({ ...workflow.generation, video_url: videoUrl })
        } else {
          setGenerationResult(workflow.generation)
        }
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The dance plan could not be generated.')
    } finally {
      planRequestInFlight.current = false
      setBusy(false)
    }
  }

  const generatePerformance = async (targetPlan: DancePlan) => {
    if (generationBusy) return
    const expectedStoryId = targetPlan.story_id
    const expectedDancePlanId = targetPlan.dance_plan_id
    const expectedChoreographyId = targetPlan.choreography_id
    setGenerationBusy(true)
    setGenerationResult(null)
    try {
      const generated = await generateStoryToDancePerformance(
        expectedStoryId,
        expectedDancePlanId,
      )
      if (
        generated.story_id === expectedStoryId
        && generated.dance_plan_id === expectedDancePlanId
        && generated.choreography_id === expectedChoreographyId
      ) {
        if (generated.status === 'completed') {
          const videoUrl = getGeneratedVideoUrl(generated) ?? generated.video_url
          if (!videoUrl) {
            throw new Error('The completed generation did not include a usable video URL.')
          }
          setGenerationResult({
            ...generated,
            video_url: videoUrl,
          })
          return
        }
        setGenerationResult(generated)
      } else {
        throw new Error('The generation result belongs to a different story or choreography.')
      }
    } catch (cause) {
      setGenerationResult({
        generation_id: '',
        story_id: expectedStoryId,
        dance_plan_id: expectedDancePlanId,
        choreography_id: expectedChoreographyId,
        status: 'failed',
        fps: null,
        duration_seconds: null,
        video_width: null,
        video_height: null,
        frame_count: null,
        skeleton_format: null,
        coordinate_convention: null,
        pose_sequence: null,
        video_url: null,
        scene_timings: [],
        movement_coverage: {
          generated_scenes: 0,
          total_scenes: targetPlan.scenes.length,
          source_supported_scenes: 0,
        },
        generator_name: null,
        generator_version: null,
        visualization_type: null,
        scenes: [],
        provenance: [],
        reason: cause instanceof Error
          ? cause.message
          : 'The dance performance generation request failed.',
        error_code: 'GENERATION_FAILED',
        limitations: [],
      })
    } finally {
      setGenerationBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-12 lg:px-10">
      <p className="eyebrow">{copy.eyebrow}</p>
      <h1 className="mt-3 font-display text-4xl text-espresso sm:text-5xl">{copy.title}</h1>
      <p className="mt-4 max-w-3xl text-sm leading-relaxed text-espresso-light">{copy.intro}</p>

      <section className="card-surface mt-8 p-6 sm:p-8">
        <div className="grid gap-5">
          <label className="block text-sm font-medium text-espresso">
            {copy.titleLabel}
            <input
              value={title}
              onChange={(event) => {
                setTitle(event.target.value)
                setRecord(null)
                setGenerationResult(null)
                if (storyId) setSearchParams({}, { replace: true })
              }}
              maxLength={120}
              className="mt-2 w-full rounded-sm border border-line bg-parchment-50 px-4 py-3 text-sm text-espresso"
            />
          </label>
          <label className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-sm border border-line px-4 py-2.5 text-sm text-espresso hover:bg-parchment-100">
            <Upload className="h-4 w-4" aria-hidden="true" />
            {copy.file}
            <input
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              className="sr-only"
              onChange={(event) => void onFileChange(event)}
            />
          </label>
          {fileName && <p className="-mt-3 text-xs text-espresso-faint">{fileName}</p>}
          <label className="block text-sm font-medium text-espresso">
            {copy.paste}
            <textarea
              value={storyText}
              onChange={(event) => updateStoryText(event.target.value)}
              rows={8}
              maxLength={20_000}
              placeholder="Write or paste the complete story here…"
              className="mt-2 w-full resize-y rounded-sm border border-line bg-parchment-50 px-4 py-3 text-sm leading-relaxed text-espresso placeholder:text-espresso-faint"
            />
            <span className="mt-1 block text-right text-xs text-espresso-faint">
              {storyText.length.toLocaleString()} / 20,000
            </span>
          </label>
          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-sm border border-danger/30 bg-danger-bg p-4 text-sm text-danger">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void generatePlan()}
              disabled={busy || !storyText.trim()}
              className="btn-primary"
            >
              {busy ? 'Creating story, choreography, and 3D animation…' : copy.generateDance}
              {!busy && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
            </button>
            <span className="text-xs text-espresso-faint">
              {languageName(language)} · Scenes stay in narrative order
            </span>
          </div>
        </div>
      </section>

      {busy && <div className="mt-8"><LoadingState label="Understanding the story, preparing scene choreography, and rendering the 3D dance…" /></div>}

      {plan && !busy && (
        <div className="mt-10 space-y-8">
          <section className="card-surface p-6 sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow">{copy.understanding}</p>
                <h2 className="mt-2 font-display text-2xl">{plan.title}</h2>
              </div>
              <span className="inline-flex items-center gap-2 rounded-full bg-grounded-bg px-3 py-1.5 text-xs text-grounded">
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                {plan.scenes.length} {copy.scenes.toLocaleLowerCase()}
              </span>
            </div>
            <p className="mt-5 text-sm leading-relaxed text-espresso-light">
              <strong className="text-espresso">{copy.summary}: </strong>{plan.summary}
            </p>
          </section>

          <section className="card-surface p-6 sm:p-8" aria-labelledby="performance-heading">
            <p className="eyebrow">Story interpretation</p>
            <h2 id="performance-heading" className="mt-2 font-display text-2xl sm:text-3xl">
              {currentGeneration?.status === 'completed' ? 'Generated Dance Video' : copy.performance}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-espresso-light">
              AI-assisted Story-to-Bharatanatyam 3D Animation. The project-built Blender renderer visualizes the planned story actions in a 3D humanoid; it is not photorealistic video or expert-validated Bharatanatyam choreography.
            </p>
            {currentGeneration?.status === 'completed' && currentVideoUrl ? (
              <>
                <video
                  key={currentGeneration.generation_id}
                  ref={videoRef}
                  className="mt-6 aspect-[8/9] max-h-[75vh] w-full rounded-sm bg-black object-contain"
                  controls
                  playsInline
                  preload="metadata"
                  src={currentVideoUrl}
                >
                  Your browser does not support HTML5 video playback.
                </video>
                <a
                  href={currentVideoUrl}
                  download={`story-to-dance-${currentGeneration.story_id}.mp4`}
                  className="btn-secondary mt-4 inline-flex items-center gap-2"
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                  Download MP4
                </a>
                <p
                  role={videoPlaybackStatus === 'error' ? 'alert' : 'status'}
                  className={`mt-3 text-sm ${videoPlaybackStatus === 'error' ? 'text-unresolved' : 'text-espresso-light'}`}
                >
                  {videoPlaybackError
                    ?? (videoPlaybackStatus === 'ready'
                      ? `Video available and browser metadata loaded (${videoRef.current?.duration.toFixed(1)} seconds).`
                      : 'Video available; checking browser playback and duration…')}
                </p>
              </>
            ) : (
              <div className="mt-6 rounded-sm border border-line bg-parchment-50 p-5">
                <p role="status" className="font-medium text-espresso">
                  {currentGeneration?.status === 'failed'
                    ? 'Dance visualization generation failed.'
                    : currentGeneration?.status === 'unavailable'
                      ? 'The procedural 3D humanoid renderer is unavailable in this environment.'
                      : 'A playable visualization will appear here after the 3D dance sequence is rendered and validated.'}
                </p>
                {currentGeneration?.reason && (
                  <p className="mt-2 text-sm text-unresolved">{currentGeneration.reason}</p>
                )}
                <details className="mt-3 text-sm text-espresso-light">
                  <summary className="cursor-pointer font-medium text-espresso">
                    About this visualization
                  </summary>
                  <p className="mt-2">
                    This is an AI-assisted procedural Blender animation, not photorealistic AI video. Classical movement names are not assigned unless supported by the project knowledge; creative movement mappings require choreographer review.
                  </p>
                </details>
              </div>
            )}
            {currentGeneration && (
              <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-xs text-espresso-faint">Generation status</dt>
                  <dd className="mt-1 font-medium capitalize text-espresso">{currentGeneration.status}</dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Duration</dt>
                  <dd className="mt-1 text-espresso">
                    {currentGeneration.duration_seconds === null
                      ? 'Unavailable'
                      : `${currentGeneration.duration_seconds.toFixed(1)} seconds`}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Scenes in choreography</dt>
                  <dd className="mt-1 text-espresso">{plan.scenes.length}</dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Source-supported movement concepts</dt>
                  <dd className="mt-1 text-espresso">
                    {currentGeneration.status === 'completed'
                      ? `${currentGeneration.movement_coverage.source_supported_scenes} / ${currentGeneration.movement_coverage.total_scenes}`
                      : 'Not generated'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Rendered scenes</dt>
                  <dd className="mt-1 text-espresso">
                    {currentGeneration.status === 'completed'
                      ? `${currentGeneration.movement_coverage.generated_scenes} / ${currentGeneration.movement_coverage.total_scenes}`
                      : 'Not generated'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Video</dt>
                  <dd className="mt-1 text-espresso">
                    {currentGeneration.status === 'completed' && currentGeneration.video_url
                      ? videoPlaybackStatus === 'error' ? 'Playback error' : 'Available'
                      : 'Unavailable'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Frames per second</dt>
                  <dd className="mt-1 text-espresso">{currentGeneration.fps ?? 'Unavailable'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-espresso-faint">Resolution</dt>
                  <dd className="mt-1 text-espresso">
                    {currentGeneration.video_width && currentGeneration.video_height
                      ? `${currentGeneration.video_width} × ${currentGeneration.video_height}`
                      : 'Unavailable'}
                  </dd>
                </div>
                <div className="sm:col-span-2 lg:col-span-4">
                  <dt className="text-xs text-espresso-faint">Generation ID</dt>
                  <dd className="mt-1 break-all font-mono text-xs text-espresso">{currentGeneration.generation_id || 'Unavailable'}</dd>
                </div>
              </dl>
            )}
            {currentGeneration?.status === 'completed' && currentGeneration.provenance.length > 0 && (
              <details className="mt-5 rounded-sm border border-line p-4">
                <summary className="cursor-pointer text-sm font-medium text-espresso">Generation details</summary>
                <dl className="mt-3 grid gap-2 text-xs text-espresso-light sm:grid-cols-2">
                  <div><dt className="font-medium">Renderer</dt><dd>{currentGeneration.generator_name} {currentGeneration.generator_version}</dd></div>
                  <div><dt className="font-medium">Generation ID</dt><dd className="break-all font-mono">{currentGeneration.generation_id}</dd></div>
                  <div><dt className="font-medium">Frame count / FPS</dt><dd>{currentGeneration.frame_count} / {currentGeneration.fps}</dd></div>
                  <div><dt className="font-medium">Provenance</dt><dd>{currentGeneration.provenance.join(' · ')}</dd></div>
                </dl>
              </details>
            )}
            {currentGeneration?.status === 'completed' && (
              <details className="mt-3 rounded-sm border border-line p-4">
                <summary className="cursor-pointer text-sm font-medium text-espresso">
                  Scene movement mapping and sources
                </summary>
                <ol className="mt-3 space-y-3">
                  {currentGeneration.scenes.map((scene) => (
                    <li key={scene.scene_id} className="border-t border-line pt-3 text-xs">
                      <p className="font-medium text-espresso">
                        Scene {scene.scene_order}: {scene.movement_concepts.length > 0
                          ? scene.movement_concepts.join(' / ')
                          : 'Procedural story-action illustration'}
                        {scene.mapping_status === 'review_required'
                          && scene.movement_concepts.length > 0
                          ? ' — combined sequence requires review'
                          : ''}
                      </p>
                      <p className="mt-1 text-espresso-light">
                        Action: {scene.action || '—'} · Target: {scene.target || '—'} · Direction: {scene.direction || '—'}
                      </p>
                      <p className="mt-1 text-espresso-light">
                        Movement phases: {scene.movement_sequence.join(' → ')}
                      </p>
                      <p className="mt-1 text-espresso-light">
                        Mudra: {scene.mudra.length ? scene.mudra.join(', ') : 'Not assigned'} · Expression: {scene.expressive_state}
                      </p>
                      <p className="mt-1 text-espresso-light">Transition: {scene.transition}</p>
                      <p className="mt-1 text-espresso-faint">Adavu: Not assigned</p>
                      {scene.source_provenance.map((source) => (
                        <p key={`${source.concept}-${source.source_reference}`} className="mt-1 text-espresso-light">
                          {source.concept}: {source.source}
                          {source.source_reference ? ` — ${source.source_reference}` : ''}
                        </p>
                      ))}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </section>

          <section className="card-surface p-6 sm:p-8" aria-labelledby="scene-timeline-heading">
            <h2 id="scene-timeline-heading" className="font-display text-2xl">Scene Timeline</h2>
            <ol className="mt-4 divide-y divide-line">
              {plan.scenes.map((scene) => {
                const timing = currentGeneration?.scene_timings.find(
                  (item) => item.scene_id === scene.scene_id,
                )
                const canSeek = currentGeneration?.status === 'completed'
                  && Boolean(currentGeneration.video_url)
                  && Boolean(timing)
                return (
                  <li key={scene.scene_id} className="py-3">
                    <button
                      type="button"
                      className="flex w-full items-start gap-3 text-left disabled:cursor-default"
                      disabled={!canSeek}
                      onClick={() => {
                        if (timing && videoRef.current) {
                          videoRef.current.currentTime = timing.start_time_seconds
                          void videoRef.current.play()
                        }
                      }}
                    >
                      <span className="font-mono text-xs text-espresso-faint">{String(scene.scene_order).padStart(2, '0')}</span>
                      <span className="flex-1 text-sm text-espresso">
                        {scene.narrative_text}
                        <span className="mt-1 block text-xs text-espresso-faint">
                          {scene.bharatanatyam_concept.length > 0
                            ? `${scene.mapping_status === 'review_required' ? 'Source-supported concepts (combined sequence requires review)' : 'Source-supported concept'}: ${scene.bharatanatyam_concept.map((item) => item.concept).join(', ')}`
                            : currentGeneration?.status === 'completed'
                              ? 'Procedural Bharatanatyam-inspired 3D humanoid visualization; no source-grounded movement concept assigned.'
                              : 'Movement visualization has not been generated.'}
                        </span>
                      </span>
                      <span className="text-xs text-espresso-faint">
                        {timing
                          ? `${timing.start_time_seconds.toFixed(1)}–${timing.end_time_seconds.toFixed(1)} s`
                          : currentGeneration?.status === 'completed' ? 'No generated segment' : 'Timing unavailable'}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </section>

          <section>
            <h2 className="mb-4 font-display text-2xl">{copy.scenes}</h2>
            <div className="space-y-4">
              {plan.scenes.map((scene) => (
                <article key={scene.scene_id} className="card-surface p-6">
                  <div className="flex items-start gap-4">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gold-300 font-display text-lg text-vermilion-500">
                      {scene.order}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-display text-xl text-espresso">Scene {scene.order}</h3>
                      <p className="text-sm leading-relaxed text-espresso-light">“{scene.narrative_text}”</p>
                      <div className="mt-5 border-t border-line pt-4">
                        <h3 className="text-sm font-semibold text-espresso">{copy.interpretation}</h3>
                        <dl className="mt-3 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.characters}</dt>
                            <dd className="mt-1 text-espresso">{scene.characters.join(', ') || '—'}</dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.action}</dt>
                            <dd className="mt-1 text-espresso">
                              {scene.action_text} <span className="text-xs text-espresso-faint">({scene.action_type})</span>
                            </dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.objects}</dt>
                            <dd className="mt-1 text-espresso">{scene.objects.join(', ') || '—'}</dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.place}</dt>
                            <dd className="mt-1 text-espresso">{scene.location || '—'}</dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.expression}</dt>
                            <dd className="mt-1 text-espresso">{scene.expressive_qualities.join(', ') || '—'}</dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.mudra}</dt>
                            <dd>
                              {scene.dance_mapping.mudras.length === 0 ? (
                                <p className="mt-1 text-sm text-unresolved">{copy.mappingUnavailable}</p>
                              ) : scene.dance_mapping.mudras.map((mapping, index) => (
                                <div key={`${mapping.concept}-${index}`} className="mt-1 text-sm">
                                  {mapping.status === 'mapped'
                                    ? <p className="font-medium text-grounded">{mapping.mudra} — {mapping.meaning}</p>
                                    : <p className="text-unresolved">{copy.mappingUnavailable}: {mapping.concept}</p>}
                                  {mapping.source && <p className="mt-1 text-xs text-espresso-faint">{mapping.source}</p>}
                                </div>
                              ))}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.bhava}</dt>
                            <dd>
                              {scene.dance_mapping.bhava.length === 0
                                ? <p className="mt-1 text-sm text-espresso-light">No source expression stated.</p>
                                : scene.dance_mapping.bhava.map((item) => <p key={item.expressive_quality} className="mt-1 text-sm text-unresolved">{item.expressive_quality} — {copy.mappingUnavailable}</p>)}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-xs text-espresso-faint">{copy.movement}</dt>
                            <dd className="mt-1 text-sm text-espresso">
                              <MovementDetails intent={scene.dance_mapping.movement.movement_intent} />
                            </dd>
                          </div>
                        </dl>
                        <SceneVisualReferences
                          references={visualReferenceState.byScene[scene.scene_id] ?? null}
                          status={visualReferenceState.status === 'idle'
                            ? 'loading'
                            : visualReferenceState.status}
                          error={visualReferenceState.error}
                        />
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="card-surface p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <Music2 className="h-5 w-5 text-vermilion-500" aria-hidden="true" />
              <h2 className="font-display text-2xl">Choreography Evidence</h2>
            </div>
            <ol className="mt-5 space-y-3">
              {plan.choreography.map((step) => (
                <li key={step.step_id} className="flex gap-3 border-l-2 border-gold-300 py-2 pl-4">
                  <span className="font-mono text-xs text-espresso-faint">{String(step.order).padStart(2, '0')}</span>
                  <div className="min-w-0">
                    <p className="text-xs italic text-espresso-faint">“{step.source_quote}”</p>
                    <p className="text-sm text-espresso">{step.story_action}</p>
                    {step.visualization_sequence.length > 0 && (
                      <p className="mt-1 text-xs text-espresso-light">
                        Planned visualization: {step.visualization_sequence.join(' → ')}
                      </p>
                    )}
                    <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                      <div><dt className="text-espresso-faint">{copy.objects}</dt><dd className="text-espresso">{step.objects.join(', ') || '—'}</dd></div>
                      <div><dt className="text-espresso-faint">{copy.place}</dt><dd className="text-espresso">{step.location || '—'}</dd></div>
                      <div><dt className="text-espresso-faint">{copy.expression}</dt><dd className="text-espresso">{step.source_expressions.join(', ') || '—'}</dd></div>
                      <div>
                        <dt className="text-espresso-faint">{copy.mudra}</dt>
                        <dd className="text-espresso">
                          {step.mudras.some((mapping) => mapping.status === 'mapped')
                            ? step.mudras.filter((mapping) => mapping.status === 'mapped').map((mapping) => `${mapping.mudra} — ${mapping.meaning}`).join('; ')
                            : copy.mappingUnavailable}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-espresso-faint">{copy.bhava}</dt>
                        <dd className="text-unresolved">
                          {step.bhava.length > 0
                            ? step.bhava.map((mapping) => `${mapping.expressive_quality} — ${copy.mappingUnavailable}`).join('; ')
                            : 'No source expression stated.'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-espresso-faint">{copy.movement}</dt>
                        <dd className="text-espresso">
                          <MovementDetails intent={step.movement_intent} />
                        </dd>
                      </div>
                    </dl>
                    <SceneVisualReferences
                      references={visualReferenceState.byScene[step.scene_id] ?? null}
                      status={visualReferenceState.status === 'idle'
                        ? 'loading'
                        : visualReferenceState.status}
                      error={visualReferenceState.error}
                    />
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <details className="rounded-sm border border-line bg-parchment-50 p-5">
            <summary className="cursor-pointer text-sm font-medium text-espresso">Technical information and limitations</summary>
            <div className="mt-4 space-y-4 text-sm text-espresso-light">
              <p>
                {currentGeneration?.status === 'completed' && currentGeneration.video_url
                  ? 'A generated dance video is available for this generation. It is a procedural story-action visualization, not canonical or expert-validated choreography.'
                  : `${plan.pose_sequence.message} ${plan.generated_performance.message}`}
              </p>
              <div className="flex flex-wrap gap-x-5 gap-y-2 font-mono text-xs text-espresso-faint">
                <span>story_id: {plan.story_id}</span>
                <span>dance_plan_id: {plan.dance_plan_id}</span>
                <span>choreography_id: {plan.choreography_id}</span>
              </div>
              <ul className="list-disc space-y-2 pl-5 text-xs leading-relaxed">
                {plan.limitations
                  .filter((limitation) => !(
                    currentGeneration?.status === 'completed'
                    && /no generated performance video exists|no curated action-to-adavu or action-to-pose sequence is available/i.test(limitation)
                  ))
                  .map((limitation) => <li key={limitation}>{limitation}</li>)}
              </ul>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
