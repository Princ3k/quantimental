'use client'

import { cn } from '@/lib/utils'
import { describeScore, toneForScore, type Tone } from '@/lib/presentation'
import { InfoTip } from '@/components/info-tip'
import type { GLOSSARY } from '@/lib/presentation'

const FILL_CLASSES: Record<Tone, string> = {
  positive: 'bg-positive',
  'mild-positive': 'bg-positive/70',
  neutral: 'bg-muted-foreground/50',
  'mild-negative': 'bg-negative/70',
  negative: 'bg-negative',
}

interface ScoreBarProps {
  label: string
  /** 0-100, or null when the underlying data was unavailable. */
  score: number | null
  glossaryKey: keyof typeof GLOSSARY
  /** Shown in place of the bar when `score` is null. */
  unavailableReason?: string | null
  className?: string
}

/**
 * A 0-100 score rendered as a word first, a bar second, a number last.
 *
 * When the score is null the bar is replaced by an explanation. That case is
 * the whole reason this component exists: the previous UI filled missing
 * sentiment with a neutral 50 and drew a half-full bar, which looked like a
 * measurement but was a placeholder.
 */
export function ScoreBar({
  label,
  score,
  glossaryKey,
  unavailableReason,
  className,
}: ScoreBarProps) {
  const unavailable = score === null

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
          {label}
          <InfoTip entry={glossaryKey} />
        </span>
        {!unavailable && (
          <span className="tabular text-xs font-semibold">
            {describeScore(score)}
            <span className="text-muted-foreground ml-1.5 font-normal">{score}/100</span>
          </span>
        )}
      </div>

      {unavailable ? (
        <p className="text-muted-foreground bg-muted/60 rounded-md px-2.5 py-2 text-xs">
          {unavailableReason ?? 'Not available for this stock.'}
        </p>
      ) : (
        <div
          className="bg-muted h-2 overflow-hidden rounded-full"
          role="meter"
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label}: ${describeScore(score)}, ${score} out of 100`}
        >
          <div
            className={cn('h-full rounded-full transition-[width] duration-500', FILL_CLASSES[toneForScore(score)])}
            style={{ width: `${Math.max(2, score)}%` }}
          />
        </div>
      )}
    </div>
  )
}
