import type { EvidenceLevel } from '@/types/analysis'

/**
 * Backends sometimes send confidence as 0–1 and sometimes as 0–100.
 * This normalizes either into a 0–100 percentage without inventing precision.
 */
export function toPercent(value?: number | null): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null
  const pct = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, pct))
}

export function formatPercent(value?: number | null, digits = 1): string | null {
  const pct = toPercent(value)
  if (pct === null) return null
  return `${pct.toFixed(digits)}%`
}

export function formatDuration(seconds?: number | null): string | null {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return null
  const total = Math.round(seconds)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

const LEVEL_LABELS: Record<string, string> = {
  high: 'High',
  moderate: 'Moderate',
  low: 'Low',
  unknown: 'Unknown',
}

export function normalizeLevel(level?: EvidenceLevel | string | null): string | null {
  if (!level) return null
  const key = level.toLowerCase()
  return LEVEL_LABELS[key] ?? level
}

/** Derives a coarse level from a numeric score when the backend doesn't provide a level label. */
export function levelFromScore(score?: number | null): EvidenceLevel | null {
  const pct = toPercent(score ?? undefined)
  if (pct === null) return null
  if (pct >= 70) return 'high'
  if (pct >= 40) return 'moderate'
  return 'low'
}

export function titleCase(value: string): string {
  return value.replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
