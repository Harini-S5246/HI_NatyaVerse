import { Moon, Sun } from 'lucide-react'
import type { Theme } from '@/hooks/useTheme'

interface ThemeToggleProps { theme: Theme; onToggle: () => void }

export default function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const isDark = theme === 'dark'
  return (
    <button type="button" onClick={onToggle} aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`} title={`Switch to ${isDark ? 'light' : 'dark'} mode`} className="relative inline-flex h-8 w-14 items-center rounded-full border border-line bg-parchment-100 p-1 transition-colors">
      <span className={`flex h-6 w-6 items-center justify-center rounded-full bg-card text-gold-600 shadow-soft transition-transform duration-300 ${isDark ? 'translate-x-6' : 'translate-x-0'}`}>
        {isDark ? <Moon className="h-3.5 w-3.5" aria-hidden="true" /> : <Sun className="h-3.5 w-3.5" aria-hidden="true" />}
      </span>
    </button>
  )
}
