'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { HowToRead } from '@/components/how-to-read'
import { MarketSummary } from '@/components/market-summary'
import { SignalDesk } from '@/components/signal-desk'
import { SiteHeader } from '@/components/site-header'
import { StockCard } from '@/components/stock-card'
import { WhatChanged } from '@/components/what-changed'
import { TickerSearch } from '@/components/ticker-search'
import { UnusualFeed } from '@/components/unusual-feed'
import { analyzeBatch, ApiError, getSignalDesk } from '@/lib/api'
import { personalNote } from '@/lib/personalise'
import { MAX_WATCHLIST, useWatchlist } from '@/lib/use-watchlist'
import type { SectorSummary, SignalFailure, StockSignal } from '@/lib/types'

const REFRESH_MS = 120_000

interface Loaded {
  key: string
  signals: StockSignal[]
  failures: SignalFailure[]
  at: Date
}

export function Dashboard() {
  const { tickers, add, remove, isFull } = useWatchlist()

  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const key = tickers.join(',')

  // Derived, not stored: results are shown only when they belong to the
  // current list. Storing a loading flag means setting it inside an effect,
  // which cascades a render on every mount.
  const current = loaded?.key === key ? loaded : null
  const loading = !error && tickers.length > 0 && current === null

  const [sectors, setSectors] = useState<SectorSummary | undefined>()

  const request = useRef<AbortController | null>(null)

  const fetchSignals = useCallback(async (symbols: string[], forKey: string) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    try {
      const response = await analyzeBatch(symbols, 'fast', controller.signal)
      if (controller.signal.aborted) return
      setLoaded({ key: forKey, signals: response.signals, failures: response.failed, at: new Date() })
      setError(null)
    } catch (caught) {
      if (controller.signal.aborted) return
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong.')
    }
  }, [])

  useEffect(() => {
    if (!key) return
    // react-hooks/set-state-in-effect cannot see through the async boundary.
    // Every update happens after the await, so no cascading render occurs.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchSignals(key.split(','), key)
  }, [key, fetchSignals])

  useEffect(() => () => request.current?.abort(), [])

  // Sector leadership, used only to connect the market read to what the user
  // holds. Failing is fine — the note simply does not render.
  useEffect(() => {
    const controller = new AbortController()
    getSignalDesk(controller.signal)
      .then((desk) => {
        if (!controller.signal.aborted && desk.available) setSectors(desk.sectors)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  /** Replace one card's data with a full-depth analysis including sentiment. */
  const applyDeepDive = useCallback((deep: StockSignal) => {
    setLoaded((previous) =>
      previous
        ? {
            ...previous,
            signals: previous.signals.map((s) => (s.ticker === deep.ticker ? deep : s)),
          }
        : previous,
    )
  }, [])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await fetchSignals(tickers, key)
    } finally {
      setRefreshing(false)
    }
  }, [fetchSignals, tickers, key])

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible' && key) void refresh()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [refresh, key])

  const signals = current?.signals ?? []
  const failures = current?.failures ?? []

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-5xl px-5 sm:px-8">
        {/* Market read */}
        <section className="py-12 sm:py-16">
          <h1 className="text-ink-3 eyebrow mb-6">Today</h1>
          <SignalDesk note={personalNote(signals, sectors)} />
        </section>

        {/* Watchlist */}
        <section className="rule-t py-10 sm:py-12">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-xl font-medium tracking-tight sm:text-2xl">Your stocks</h2>
              {current && signals.length > 0 && (
                <div className="mt-2.5">
                  <MarketSummary signals={signals} />
                </div>
              )}
            </div>
            <div className="flex items-end gap-5">
              <TickerSearch onSelect={add} existing={tickers} disabled={isFull} />
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loading || refreshing || tickers.length === 0}
                className="text-ink-3 hover:text-ink pb-1.5 text-[0.8125rem] transition-colors disabled:opacity-40"
              >
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>

          {isFull && (
            <p className="text-ink-3 mb-6 text-[0.8125rem]">
              Following the maximum of {MAX_WATCHLIST} stocks. Remove one to add another.
            </p>
          )}

          {error && (
            <div className="mb-8">
              <p className="text-down text-sm">{error}</p>
              <button
                type="button"
                onClick={() => void refresh()}
                className="text-ink-3 hover:text-ink mt-2 text-[0.8125rem] transition-colors"
              >
                Try again
              </button>
            </div>
          )}

          {failures.length > 0 && (
            <ul className="mb-8 space-y-1.5">
              {failures.map((failure) => (
                <li key={failure.ticker} className="text-ink-3 flex items-baseline gap-3 text-[0.8125rem]">
                  <span className="font-mono">{failure.ticker}</span>
                  <span className="flex-1">{failure.reason}</span>
                  <button
                    type="button"
                    onClick={() => remove(failure.ticker)}
                    className="hover:text-ink transition-colors"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          {current && signals.length > 0 && <WhatChanged signals={signals} />}

          {loading ? (
            <div className="grid gap-4 md:grid-cols-2" aria-busy="true">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-rule/40 h-64 animate-pulse rounded-lg" />
              ))}
            </div>
          ) : signals.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              {signals.map((signal) => (
                <StockCard
                  key={signal.ticker}
                  signal={signal}
                  onRemove={remove}
                  onDeepDive={applyDeepDive}
                />
              ))}
            </div>
          ) : (
            !error && (
              <p className="text-ink-3 py-12 text-sm">
                No stocks yet. Search above to add your first — try AAPL, or a company name.
              </p>
            )
          )}

          {/* Why the app is worth opening on a day your own stocks did nothing.
              Placed below the watchlist: someone who came to check their own
              holdings should see those first. */}
          <div className="mt-12">
            <UnusualFeed onPick={isFull ? undefined : add} />
          </div>

          <div className="mt-10">
            <HowToRead />
          </div>
        </section>

        <footer className="rule-t text-ink-3 py-8 text-xs leading-relaxed">
          <p className="max-w-2xl">
            Quantimental summarises public price data and, where available, public news and social
            posts. It cannot predict the future, it does not know your circumstances, and it can be
            wrong. This is not financial advice.
          </p>
          {current && (
            <p className="tnum mt-3">
              Updated {current.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
          )}
        </footer>
      </main>
    </div>
  )
}
