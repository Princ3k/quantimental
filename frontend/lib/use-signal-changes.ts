'use client'

import { useMemo } from 'react'

import { useStoredValue } from './use-local-storage'
import type { RecommendationAction, StockSignal } from './types'

const STORAGE_KEY = 'quantimental.lastSeenVerdicts'

/** What a verdict was, last time this browser looked. */
type Seen = Record<string, RecommendationAction>

export interface VerdictChange {
  ticker: string
  from: RecommendationAction
  to: RecommendationAction
  /** True when the move is toward the bullish end of the scale. */
  improved: boolean
}

const RANK: Record<RecommendationAction, number> = {
  strong_sell: 0,
  sell: 1,
  hold: 2,
  buy: 3,
  strong_buy: 4,
}

function parseSeen(raw: string | null): Seen {
  if (raw === null) return {}
  const parsed: unknown = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
  return parsed as Seen
}

/**
 * What changed since this browser last looked.
 *
 * Deliberately local rather than server-side. "Three stocks changed since
 * yesterday" is the one thing that makes this worth reopening, and it does not
 * need accounts, storage or a push pipeline to deliver — only a record of what
 * was last shown *to this person*, which localStorage already is.
 *
 * Returns the changes and a `commit` to call once they have been displayed.
 * Marking them seen on render would mean a refresh silently erased them.
 */
export function useSignalChanges(signals: StockSignal[]) {
  const [seen, setSeen] = useStoredValue<Seen>(STORAGE_KEY, {}, parseSeen)

  const changes = useMemo<VerdictChange[]>(() => {
    return signals
      .filter((signal) => {
        const previous = seen[signal.ticker]
        return previous !== undefined && previous !== signal.recommendation.action
      })
      .map((signal) => {
        const from = seen[signal.ticker]
        const to = signal.recommendation.action
        return { ticker: signal.ticker, from, to, improved: RANK[to] > RANK[from] }
      })
  }, [signals, seen])

  /** Record the current verdicts as seen. Call after showing the changes. */
  const commit = () => {
    if (signals.length === 0) return
    const next: Seen = { ...seen }
    for (const signal of signals) next[signal.ticker] = signal.recommendation.action
    setSeen(next)
  }

  /** True on a first visit, when there is nothing to compare against. */
  const firstVisit = Object.keys(seen).length === 0

  return { changes, commit, firstVisit }
}
