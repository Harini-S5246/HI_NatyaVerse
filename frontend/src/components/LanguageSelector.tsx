import { Fragment, useRef, useState } from 'react'
import { ChevronDown, Languages } from 'lucide-react'
import type { SupportedLanguage } from '@/types/analysis'
import { LANGUAGES } from '@/utils/languages'

interface LanguageSelectorProps {
  value: SupportedLanguage
  onChange: (language: SupportedLanguage) => void
  variant?: 'nav' | 'panel'
}

export default function LanguageSelector({ value, onChange, variant = 'nav' }: LanguageSelectorProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const current = LANGUAGES.find((lang) => lang.value === value) ?? LANGUAGES[0]

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className={
          variant === 'nav'
            ? 'inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs font-medium text-espresso-light transition-colors hover:border-gold-300 hover:text-espresso'
            : 'inline-flex w-full items-center justify-between gap-2 rounded-sm border border-line bg-parchment-50 px-4 py-2.5 text-sm text-espresso'
        }
      >
        <Languages className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{current.nativeLabel}</span>
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>

      {open && (
        <Fragment>
          <button
            type="button"
            aria-label="Close language menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <ul
            role="listbox"
            className="absolute right-0 z-20 mt-2 w-44 overflow-hidden rounded-card border border-line bg-card shadow-lift"
          >
            {LANGUAGES.map((lang) => (
              <li key={lang.value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={lang.value === value}
                  onClick={() => {
                    onChange(lang.value)
                    setOpen(false)
                  }}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm transition-colors hover:bg-parchment-100 ${
                    lang.value === value ? 'text-vermilion-500' : 'text-espresso'
                  }`}
                >
                  <span>{lang.nativeLabel}</span>
                  <span className="text-xs text-espresso-faint">{lang.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </Fragment>
      )}
    </div>
  )
}
