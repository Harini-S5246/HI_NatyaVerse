import { useCallback, useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'

const ACCEPTED_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm']
const ACCEPTED_EXTENSIONS = ['.mp4', '.mov', '.avi', '.webm']
const MAX_SIZE_BYTES = 500 * 1024 * 1024 // 500MB

interface VideoUploaderProps {
  onFileSelected: (file: File) => void
}

function isAcceptedFile(file: File): boolean {
  if (ACCEPTED_TYPES.includes(file.type)) return true
  const lower = file.name.toLowerCase()
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export default function VideoUploader({ onFileSelected }: VideoUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateAndEmit = useCallback(
    (file: File | undefined) => {
      if (!file) {
        setValidationError('No file was selected. Choose a performance video to continue.')
        return
      }
      if (!isAcceptedFile(file)) {
        setValidationError('Unsupported file type. Please upload an MP4, MOV, AVI or WEBM video.')
        return
      }
      if (file.size > MAX_SIZE_BYTES) {
        setValidationError('This file is larger than 500MB. Please upload a smaller video.')
        return
      }
      setValidationError(null)
      onFileSelected(file)
    },
    [onFileSelected],
  )

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setIsDragging(false)
          validateAndEmit(event.dataTransfer.files?.[0])
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-20 text-center transition-colors duration-200 ${
          isDragging ? 'border-vermilion-500 bg-vermilion-50' : 'border-line bg-parchment-100/60 hover:border-gold-400'
        }`}
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-gold-400/50 text-gold-600">
          <UploadCloud className="h-6 w-6" aria-hidden="true" />
        </div>
        <p className="mt-6 text-lg text-espresso">
          Drop your performance here <span className="text-espresso-faint">or</span>
        </p>
        <span className="btn-secondary mt-4">Browse Video</span>
        <p className="mt-6 text-xs uppercase tracking-widest2 text-espresso-faint">MP4 · MOV · AVI · WEBM</p>

        <input
          ref={inputRef}
          type="file"
          accept={[...ACCEPTED_TYPES, ...ACCEPTED_EXTENSIONS].join(',')}
          className="sr-only"
          onChange={(event) => validateAndEmit(event.target.files?.[0])}
        />
      </div>

      {validationError && (
        <p role="alert" className="mt-4 text-sm text-danger">
          {validationError}
        </p>
      )}
    </div>
  )
}
