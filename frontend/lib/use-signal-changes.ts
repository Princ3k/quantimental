'use client'

import { useMemo } from 'react'

import { useStoredValue } from './use-local-storage'
import type { Situation, StockSignal } from './types'

const STORAGE_KEY = 'quantimental.lastSeenStates'

type State = Situation['state']

/** What each stock was doing, last time this browser looked. */
type Seen = Record<string, State>

export interface StateChange {
  ticker: string
  from: State
  to: State
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
 * Tracks the *described state* — rising, falling, steady over two weeks — not a
 * buy/sell verdict. A stock turning from rising to falling is an observable
 * fact about its price; a stock moving from "hold" to "sell" was a change in
 * our opinion, which is a much weaker reason to ask for someone's attention.
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

  const changes = useMemo<StateChange[]>(() => {
    return signals
      .filter((signal) => {
        const previous = seen[signal.ticker]
        return previous !== undefined && previous !== signal.situation.state
      })
      .map((signal) => ({
        ticker: signal.ticker,
        from: seen[signal.ticker],
        to: signal.situation.state,
      }))
  }, [signals, seen])

  /** Record the current states as seen. Call after showing the changes. */
  const commit = () => {
    if (signals.length === 0) return
    const next: Seen = { ...seen }
    for (const signal of signals) next[signal.ticker] = signal.situation.state
    setSeen(next)
  }

  /** True on a first visit, when there is nothing to compare against. */
  const firstVisit = Object.keys(seen).length === 0

  return { changes, commit, firstVisit }
}
