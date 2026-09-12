'use client'

import { ArrowDown, ArrowUp, Minus, TrendingDown, TrendingUp } from 'lucide-react'

import { cn } from '@/lib/utils'
import { ACTION_TONE, describeConfidence, type Tone } from '@/lib/presentation'
import type { RecommendationAction } from '@/lib/types'

const TONE_CLASSES: Record<Tone, string> = {
  positive: 'bg-positive text-positive-foreground',
  'mild-positive': 'bg-positive-subtle text-positive',
  neutral: 'bg-muted text-muted-foreground',
  'mild-negative': 'bg-negative-subtle text-negative',
  negative: 'bg-negative text-negative-foreground',
}

const ACTION_ICON: Record<RecommendationAction, typeof TrendingUp> = {
  strong_buy: TrendingUp,
  buy: ArrowUp,
  hold: Minus,
  sell: ArrowDown,
  strong_sell: TrendingDown,
}

interface VerdictProps {
  action: RecommendationAction
  label: string
  size?: 'sm' | 'lg'
  className?: string
}

/**
 * The headline Buy / Hold / Sell pill.
 *
 * Always shows an icon *and* the word, so the verdict survives both
 * greyscale printing and colour vision deficiency.
 */
export function Verdict({ action, label, size = 'sm', className }: VerdictProps) {
  const Icon = ACTION_ICON[action]

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full font-semibold',
        TONE_CLASSES[ACTION_TONE[action]],
        size === 'lg' ? 'px-4 py-1.5 text-base' : 'px-3 py-1 text-sm',
        className,
      )}
    >
      <Icon className={size === 'lg' ? 'size-4' : 'size-3.5'} aria-hidden />
      {label}
    </span>
  )
}

interface ConfidenceProps {
  value: number
  className?: string
}

/**
 * Confidence shown as a labelled bar.
 *
 * The word ("Moderate confidence") leads and the number follows, because
 * "53%" on its own invites false precision — what matters is the band.
 */
export function ConfidenceMeter({ value, className }: ConfidenceProps) {
  const { label, meaning } = describeConfidence(value)

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-muted-foreground tabular text-xs">{value}%</span>
      </div>
      <div
        className="bg-muted h-1.5 overflow-hidden rounded-full"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Confidence: ${label}`}
      >
        <div
          className="bg-primary h-full rounded-full transition-[width] duration-500"
          style={{ width: `${Math.max(2, value)}%` }}
        />
      </div>
      <p className="text-muted-foreground text-xs">{meaning}</p>
    </div>
  )
}
