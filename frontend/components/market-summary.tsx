'use client'

import type { Situation, StockSignal } from '@/lib/types'

type State = Situation['state']

const ORDER: State[] = ['rising', 'falling', 'steady']
const LABEL: Record<State, string> = {
  rising: 'Rising',
  falling: 'Falling',
  steady: 'Steady',
}

/**
 * A tally of what the stocks on this list are doing.
 *
 * Counts observed two-week direction, not verdicts. "Four rising, two falling"
 * is a fact about the list; "four buys" was a summary of our own opinions,
 * which told the reader nothing they could verify.
 *
 * Scoped to *your list*, not "the market" — an earlier version presented the
 * same count as overall market mood alongside a hard-coded VIX that was never
 * fetched from anywhere.
 */
export function MarketSummary({ signals }: { signals: StockSignal[] }) {
  if (signals.length === 0) return null

  const counts = signals.reduce<Partial<Record<State, number>>>((acc, s) => {
    acc[s.situation.state] = (acc[s.situation.state] ?? 0) + 1
    return acc
  }, {})

  return (
    <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
      {ORDER.filter((state) => counts[state]).map((state) => (
        <div key={state} className="flex items-baseline gap-1.5">
          <dt className="text-ink-3 text-[0.8125rem]">{LABEL[state]}</dt>
          <dd className="tnum font-mono text-[0.8125rem] font-medium">{counts[state]}</dd>
        </div>
      ))}
    </dl>
  )
}
