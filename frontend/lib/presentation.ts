/**
 * Presentation helpers: backend values rendered as language.
 *
 * Everything user-facing that involves a judgement call about wording lives
 * here, so the vocabulary stays consistent across the app.
 *
 * The house rule: **no bare jargon on screen.** Where a technical term would
 * appear, it is either renamed to something self-explanatory or stated with
 * its meaning alongside it — never abbreviated and left for the reader to
 * decode. Wording that depends on a measurement (momentum, for one) comes from
 * the backend, so a card cannot contradict itself.
 */

import type { TrendLabel, Volatility } from './types'

export const TREND_LABEL: Record<TrendLabel, string> = {
  strong_uptrend: 'Rising steadily',
  uptrend: 'Drifting up',
  sideways: 'Going nowhere',
  downtrend: 'Drifting down',
  strong_downtrend: 'Falling steadily',
}

export const VOLATILITY_LABEL: Record<Volatility, string> = {
  high: 'Bumpy',
  moderate: 'Normal',
  low: 'Calm',
}

/** Price in US dollars. */
export function formatPrice(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/** Percentage change with an explicit sign. */
export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

/** Compact share volume, e.g. 49.4M. */
export function formatVolume(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value)
}
