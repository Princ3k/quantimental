'use client'

import { Verdict } from '@/components/verdict'
import type { RecommendationAction, StockSignal } from '@/lib/types'

interface MarketSummaryProps {
  signals: StockSignal[]
}

const ORDER: RecommendationAction[] = ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']

const LABELS: Record<RecommendationAction, string> = {
  strong_buy: 'Strong Buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong Sell',
}

/**
 * A one-line read on the user's whole list.
 *
 * Scoped carefully: this summarises *the stocks on this list*, not "the
 * market". The earlier version presented the same tally as overall market
 * mood, alongside a hard-coded VIX of 16.2 that was never fetched from
 * anywhere.
 */
export function MarketSummary({ signals }: MarketSummaryProps) {
  if (signals.length === 0) return null

  const counts = signals.reduce<Record<string, number>>((acc, signal) => {
    const action = signal.recommendation.action
    acc[action] = (acc[action] ?? 0) + 1
    return acc
  }, {})

  const positive = (counts.strong_buy ?? 0) + (counts.buy ?? 0)
  const negative = (counts.sell ?? 0) + (counts.strong_sell ?? 0)

  let headline: string
  if (positive > negative * 2) {
    headline = `Most of your list is looking positive right now.`
  } else if (negative > positive * 2) {
    headline = `Most of your list is looking weak right now.`
  } else {
    headline = `Your list is mixed — some strength, some weakness.`
  }

  return (
    <section
      aria-label="Summary of your list"
      className="bg-card border-border rounded-xl border p-4"
    >
      <p className="text-sm font-medium">{headline}</p>
      <p className="text-muted-foreground mt-0.5 text-xs">
        Across {signals.length} {signals.length === 1 ? 'stock' : 'stocks'} you are following.
      </p>

      <ul className="mt-3 flex flex-wrap gap-2">
        {ORDER.filter((action) => counts[action]).map((action) => (
          <li key={action} className="flex items-center gap-1.5">
            <Verdict action={action} label={LABELS[action]} />
            <span className="text-muted-foreground tabular text-xs">{counts[action]}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
