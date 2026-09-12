'use client'

import { useCallback } from 'react'

import { useStoredValue } from './use-local-storage'

const STORAGE_KEY = 'quantimental.watchlist'

/** Shown to a first-time visitor so the dashboard is never empty. */
export const DEFAULT_WATCHLIST = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA']

/** A batch fans out to one upstream call per ticker; the backend caps it at 30. */
export const MAX_WATCHLIST = 30

/**
 * Parse the stored watchlist, tolerating anything.
 *
 * Storage can hold data written by an older build, hand-edited JSON, or
 * nothing at all, so every failure path resolves to the defaults rather than
 * throwing during render.
 */
function parseWatchlist(raw: string | null): string[] {
  if (raw === null) return DEFAULT_WATCHLIST

  const parsed: unknown = JSON.parse(raw)
  if (!Array.isArray(parsed)) return DEFAULT_WATCHLIST

  const tickers = parsed
    .filter((entry): entry is string => typeof entry === 'string')
    .map((entry) => entry.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, MAX_WATCHLIST)

  // An empty stored list is a deliberate "I removed everything" state, so it
  // is preserved rather than being refilled with the defaults.
  return Array.from(new Set(tickers))
}

/** The user's watchlist, persisted to this browser and synced across tabs. */
export function useWatchlist() {
  const [tickers, setTickers] = useStoredValue(STORAGE_KEY, DEFAULT_WATCHLIST, parseWatchlist)

  const add = useCallback(
    (ticker: string) => {
      const symbol = ticker.trim().toUpperCase()
      if (!symbol || tickers.includes(symbol) || tickers.length >= MAX_WATCHLIST) return
      setTickers([...tickers, symbol])
    },
    [tickers, setTickers],
  )

  const remove = useCallback(
    (ticker: string) => {
      setTickers(tickers.filter((entry) => entry !== ticker.toUpperCase()))
    },
    [tickers, setTickers],
  )

  const reset = useCallback(() => setTickers(DEFAULT_WATCHLIST), [setTickers])

  return { tickers, add, remove, reset, isFull: tickers.length >= MAX_WATCHLIST }
}
