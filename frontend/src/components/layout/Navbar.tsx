import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import LanguageSelector from '@/components/LanguageSelector'
import ThemeToggle from '@/components/common/ThemeToggle'
import { useLastAnalysisId } from '@/hooks/useLastAnalysisId'
import type { SupportedLanguage } from '@/types/analysis'
import type { Theme } from '@/hooks/useTheme'

interface NavbarProps {
  language: SupportedLanguage
  onLanguageChange: (language: SupportedLanguage) => void
  theme: Theme
  onThemeToggle: () => void
}

export default function Navbar({ language, onLanguageChange, theme, onThemeToggle }: NavbarProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { lastAnalysisId } = useLastAnalysisId()

  const LINKS = [
    { to: '/', label: 'Home' },
    { to: '/analyze', label: 'Analyze' },
    { to: lastAnalysisId ? `/analysis/${lastAnalysisId}` : '/analyze', label: 'Evidence' },
    { to: lastAnalysisId ? `/story/${lastAnalysisId}` : '/analyze', label: 'Story' },
    { to: '/create-dance', label: 'Create Dance' },
  ]

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-parchment-50/90 shadow-[0_1px_16px_rgb(43_35_32/0.04)] backdrop-blur transition-colors duration-300">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-10">
        <Link to="/" className="flex items-center gap-2.5" onClick={() => setMobileOpen(false)}>
          <span className="flex h-8 w-8 items-center justify-center rounded-full border border-vermilion-500/40">
            <svg viewBox="0 0 24 24" className="h-4 w-4 text-vermilion-500" fill="none" aria-hidden="true">
              <path
                d="M12 3c4 3.4 6 7.4 6 11a6 6 0 0 1-12 0c0-3.6 2-7.6 6-11Z"
                stroke="currentColor"
                strokeWidth="1.6"
              />
            </svg>
          </span>
          <span className="font-display text-lg tracking-wide text-espresso">
            HI-Natya <span className="text-vermilion-500">Verse</span>
          </span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {LINKS.map((link) => (
            <NavLink
              key={link.label}
              to={link.to}
              className={({ isActive }) =>
                `relative py-2 text-sm tracking-wide transition-colors after:absolute after:inset-x-0 after:-bottom-0.5 after:h-px after:bg-vermilion-500 after:transition-transform ${
                  isActive ? 'text-vermilion-500 after:scale-x-100' : 'text-espresso-light hover:text-espresso after:scale-x-0'
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-4 md:flex">
          <LanguageSelector value={language} onChange={onLanguageChange} />
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
          <Link to="/analyze" className="btn-primary py-2.5 text-xs">
            Analyze a Performance
          </Link>
        </div>

        <button
          type="button"
          className="inline-flex items-center justify-center rounded-sm border border-line p-2 md:hidden"
          aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((prev) => !prev)}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-line bg-parchment-50 px-6 py-5 md:hidden">
          <nav className="flex flex-col gap-4">
            {LINKS.map((link) => (
              <NavLink
                key={link.label}
                to={link.to}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `text-sm ${isActive ? 'text-vermilion-500' : 'text-espresso-light'}`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-5 flex items-center justify-between gap-4">
            <LanguageSelector value={language} onChange={onLanguageChange} />
            <ThemeToggle theme={theme} onToggle={onThemeToggle} />
            <Link to="/analyze" className="btn-primary py-2.5 text-xs" onClick={() => setMobileOpen(false)}>
              Analyze
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
