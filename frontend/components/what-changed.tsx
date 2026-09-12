'use client'

import { useSignalChanges } from '@/lib/use-signal-changes'
import { cn } from '@/lib/utils'
import type { StockSignal } from '@/lib/types'

const LABEL = {
  strong_buy: 'Strong buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong sell',
} as const

/**
 * What moved since this browser last looked.
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
            <span className="text-ink font-mono">{change.ticker}</span>{' '}
            {LABEL[change.from]} →{' '}
            <span className={cn(change.improved ? 'text-up' : 'text-down')}>
              {LABEL[change.to]}
            </span>
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
