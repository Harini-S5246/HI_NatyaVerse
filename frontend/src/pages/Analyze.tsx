import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, LoaderCircle } from 'lucide-react'
import VideoUploader from '@/components/upload/VideoUploader'
import VideoPreview from '@/components/upload/VideoPreview'
import ErrorMessage from '@/components/common/ErrorMessage'
import {
  classifyBhavas,
  classifyMudras,
  extractVideoFrames,
  fuse,
  uploadVideo,
  type VideoUploadResponse,
} from '@/services/api'
import type { ApiErrorPayload } from '@/types/analysis'

type Stage = 'select' | 'uploading' | 'extracting' | 'analyzing' | 'success'

interface AnalysisProgress {
  mudra?: boolean
  bhava?: boolean
  fusion?: boolean
}

export default function Analyze() {
  const navigate = useNavigate()
  const [stage, setStage] = useState<Stage>('select')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadResult, setUploadResult] = useState<VideoUploadResponse | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress>({})
  const [uploadError, setUploadError] = useState<ApiErrorPayload | null>(null)

  const extractFrames = async (upload: VideoUploadResponse) => {
    setStage('extracting')
    setUploadError(null)

    try {
      await extractVideoFrames(upload.video_id, 1.0)
      await runAnalysisPipeline(upload.video_id)
    } catch (error) {
      setUploadError(error as ApiErrorPayload)
      setStage('select')
    }
  }

  const runAnalysisPipeline = async (videoId: string) => {
    setStage('analyzing')
    setUploadError(null)

    try {
      // Step 1: Run Mudra classification
      await classifyMudras(videoId)
      setAnalysisProgress((p) => ({ ...p, mudra: true }))

      // Step 2: Run Bhava classification
      await classifyBhavas(videoId)
      setAnalysisProgress((p) => ({ ...p, bhava: true }))

      // Step 3: Run Fusion
      await fuse(videoId)
      setAnalysisProgress((p) => ({ ...p, fusion: true }))

      setStage('success')
      
      // Navigate to analysis results after a short delay
      setTimeout(() => {
        navigate(`/analysis/${videoId}`)
      }, 1500)
    } catch (error) {
      setUploadError(error as ApiErrorPayload)
      setStage('select')
      setAnalysisProgress({})
    }
  }

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadError({ message: 'No video was selected. Choose a performance video to continue.', code: 'MISSING_VIDEO' })
      return
    }

    if (uploadResult) {
      await extractFrames(uploadResult)
      return
    }

    setStage('uploading')
    setUploadError(null)

    try {
      const result = await uploadVideo(selectedFile)
      setUploadResult(result)
      await extractFrames(result)
    } catch (error) {
      setUploadError(error as ApiErrorPayload)
      setStage('select')
    }
  }

  const resetUpload = () => {
    setSelectedFile(null)
    setUploadResult(null)
    setUploadError(null)
    setAnalysisProgress({})
    setStage('select')
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-20 lg:px-10">
      <p className="eyebrow mb-4">Step 1 of 3</p>
      <h1 className="text-4xl text-espresso sm:text-5xl">Analyze a Performance</h1>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-espresso-light">
        Upload a Bharatanatyam performance to begin multimodal analysis.
      </p>

      <div className="mt-12">
        {stage === 'select' && !selectedFile && (
          <VideoUploader
            onFileSelected={(file) => {
              setSelectedFile(file)
              setUploadResult(null)
              setUploadError(null)
            }}
          />
        )}

        {stage === 'select' && selectedFile && (
          <VideoPreview
            file={selectedFile}
            onRemove={resetUpload}
            onAnalyze={handleUpload}
          />
        )}

        {stage === 'uploading' && selectedFile && (
          <VideoPreview file={selectedFile} onRemove={resetUpload} onAnalyze={handleUpload} isSubmitting />
        )}

        {stage === 'extracting' && uploadResult && (
          <div className="card-surface animate-fadeIn px-6 py-10 text-center">
            <LoaderCircle className="mx-auto h-10 w-10 animate-spin text-gold-600" aria-hidden="true" />
            <h2 className="mt-4 font-display text-2xl text-espresso">Extracting performance frames</h2>
            <p className="mt-2 text-sm text-espresso-light">
              Video uploaded successfully. Preparing sampled frames for analysis…
            </p>
          </div>
        )}

        {stage === 'analyzing' && uploadResult && (
          <div className="card-surface animate-fadeIn px-6 py-10">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                {analysisProgress.mudra ? (
                  <CheckCircle2 className="h-5 w-5 text-success shrink-0" aria-hidden="true" />
                ) : (
                  <LoaderCircle className="h-5 w-5 animate-spin text-gold-600 shrink-0" aria-hidden="true" />
                )}
                <span className="text-base text-espresso">Mudra analysis</span>
              </div>

              <div className="flex items-center gap-3">
                {analysisProgress.bhava ? (
                  <CheckCircle2 className="h-5 w-5 text-success shrink-0" aria-hidden="true" />
                ) : (
                  <div className="h-5 w-5 rounded-full border-2 border-espresso-faint/30 shrink-0" />
                )}
                <span className="text-base text-espresso">Bhava analysis</span>
              </div>

              <div className="flex items-center gap-3">
                {analysisProgress.fusion ? (
                  <CheckCircle2 className="h-5 w-5 text-success shrink-0" aria-hidden="true" />
                ) : (
                  <div className="h-5 w-5 rounded-full border-2 border-espresso-faint/30 shrink-0" />
                )}
                <span className="text-base text-espresso">Fusion alignment</span>
              </div>

            </div>
          </div>
        )}

        {stage === 'success' && uploadResult && (
          <div className="card-surface animate-fadeIn px-6 py-10 text-center">
            <CheckCircle2 className="mx-auto h-10 w-10 text-success" aria-hidden="true" />
            <h2 className="mt-4 font-display text-2xl text-espresso">Analysis complete</h2>
            <p className="mt-2 text-sm text-espresso-light">{uploadResult.filename}</p>
            <p className="mt-2 text-xs text-espresso-faint">Redirecting to results…</p>
          </div>
        )}

        {uploadError && (
          <div className="mt-6">
            <ErrorMessage error={uploadError} onRetry={handleUpload} />
          </div>
        )}
      </div>
    </div>
  )
}
