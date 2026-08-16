import { useCallback, useState } from 'react'
import type { SupportedLanguage } from '@/types/analysis'
import { DEFAULT_LANGUAGE } from '@/utils/languages'

const STORAGE_KEY = 'hi-natya-verse:language'

function readInitialLanguage(): SupportedLanguage {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE.value
  const stored = window.sessionStorage.getItem(STORAGE_KEY)
  return (stored as SupportedLanguage) || DEFAULT_LANGUAGE.value
}

export function useLanguage() {
  const [language, setLanguageState] = useState<SupportedLanguage>(readInitialLanguage)

  const setLanguage = useCallback((next: SupportedLanguage) => {
    setLanguageState(next)
    window.sessionStorage.setItem(STORAGE_KEY, next)
  }, [])

  return { language, setLanguage }
}
