import type { LanguageOption } from '@/types/analysis'

export const LANGUAGES: LanguageOption[] = [
  { value: 'English', label: 'English', nativeLabel: 'English' },
  { value: 'Tamil', label: 'Tamil', nativeLabel: 'தமிழ்' },
  { value: 'Hindi', label: 'Hindi', nativeLabel: 'हिन्दी' },
  { value: 'Malayalam', label: 'Malayalam', nativeLabel: 'മലയാളം' },
  { value: 'Telugu', label: 'Telugu', nativeLabel: 'తెలుగు' },
  { value: 'Kannada', label: 'Kannada', nativeLabel: 'ಕನ್ನಡ' },
  { value: 'Bengali', label: 'Bengali', nativeLabel: 'বাংলা' },
]

export const DEFAULT_LANGUAGE = LANGUAGES[0]
