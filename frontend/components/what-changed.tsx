'use client'

import { useSignalChanges } from '@/lib/use-signal-changes'
import { cn } from '@/lib/utils'
import type { StockSignal } from '@/lib/types'

const LABEL = {
  rising: 'rising',
  falling: 'falling',
  steady: 'steady',
} as const

/* Colour marks direction of price, not approval. Steady is neither. */
const TONE = {
  rising: 'text-up',
  falling: 'text-down',
  steady: 'text-ink-2',
} as const

/**
 * What moved since this browser last looked.
 *
 * Reports a change in what a stock is *doing* — rising, falling, steady — which
 * is checkable against its chart. It used to report a change in our verdict,
 * which asked the reader to care that our opinion had moved.
 *
 * The reason to come back. Renders nothing on a first visit or a quiet day,
 * which is most days — a "nothing changed" banner every load would train
 * people to ignore the space entirely.
 */
export function WhatChanged({ signals }: { signals: StockSignal[] }) {
  const { changes, commit, firstVisit } = useSignalChanges(signals)

  if (firstVisit || changes.length === 0) return null

  return (
    <div className="border-rule-strong mb-8 border-l-2 pl-4">
      <p className="text-[0.9375rem]">
        {changes.length === 1 ? 'One stock changed' : `${changes.length} stocks changed`} since you
        last looked.
      </p>
      <ul className="mt-2 space-y-1">
        {changes.map((change) => (
          <li key={change.ticker} className="text-ink-2 text-[0.8125rem]">
            <span className="text-ink font-mono">{change.ticker}</span> was{' '}
            {LABEL[change.from]}, now{' '}
            <span className={cn(TONE[change.to])}>{LABEL[change.to]}</span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={commit}
        className="text-ink-3 hover:text-ink mt-2.5 text-[0.8125rem] transition-colors"
      >
        Dismiss
      </button>
    </div>
  )
}
