'use client'

import type { RecommendationAction, StockSignal } from '@/lib/types'

const ORDER: RecommendationAction[] = ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']
const SHORT: Record<RecommendationAction, string> = {
  strong_buy: 'Strong buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong sell',
}

/**
 * A tally of the verdicts on this list.
 *
 * Scoped to *your list*, not "the market" — the previous version presented the
 * same count as overall market mood alongside a hard-coded VIX that was never
 * fetched from anywhere.
 */
export function MarketSummary({ signals }: { signals: StockSignal[] }) {
  if (signals.length === 0) return null

  const counts = signals.reduce<Partial<Record<RecommendationAction, number>>>((acc, s) => {
    acc[s.recommendation.action] = (acc[s.recommendation.action] ?? 0) + 1
    return acc
  }, {})

  return (
    <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
      {ORDER.filter((a) => counts[a]).map((action) => (
        <div key={action} className="flex items-baseline gap-1.5">
          <dt className="text-ink-3 text-[0.8125rem]">{SHORT[action]}</dt>
          <dd className="tnum font-mono text-[0.8125rem] font-medium">{counts[action]}</dd>
        </div>
      ))}
    </dl>
  )
}
