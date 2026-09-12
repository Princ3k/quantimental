'use client'

import { cn } from '@/lib/utils'
import type { RecommendationAction } from '@/lib/types'

/*
 * The verdict is deliberately quiet.
 *
 * A backtest of 1,888 observations found no statistically significant edge in
 * these calls, and a monotonic inversion suggesting the opposite of what they
 * assert. Rendering them as large coloured buttons would overstate what they
 * are worth. They are a label on a reading, not a call to action, and they are
 * styled like one.
 */

const LABEL: Record<RecommendationAction, string> = {
  strong_buy: 'Strong buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong sell',
}

const TONE: Record<RecommendationAction, string> = {
  strong_buy: 'text-up',
  buy: 'text-up',
  hold: 'text-ink-2',
  sell: 'text-down',
  strong_sell: 'text-down',
}

/** A filled dot for the strong calls, hollow otherwise — weight without colour. */
const FILLED: Record<RecommendationAction, boolean> = {
  strong_buy: true,
  buy: false,
  hold: false,
  sell: false,
  strong_sell: true,
}

export function Verdict({
  action,
  className,
}: {
  action: RecommendationAction
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-sm font-medium', TONE[action], className)}>
      <span
        aria-hidden
        className={cn(
          'size-1.5 rounded-full',
          FILLED[action] ? 'bg-current' : 'border border-current',
        )}
      />
      {LABEL[action]}
    </span>
  )
}

/**
 * Confidence as a sentence, not a meter.
 *
 * A progress bar invites the reader to compare fill levels at a glance, which
 * implies a precision this number does not have. The word carries it.
 */
export function Confidence({ value }: { value: number }) {
  const label = value >= 70 ? 'High' : value >= 45 ? 'Moderate' : value >= 25 ? 'Low' : 'Very low'
  return (
    <span className="text-ink-3 tnum text-sm">
      {label} confidence · {value}%
    </span>
  )
}
