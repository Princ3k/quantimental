'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { TooltipProvider } from '@/components/ui/tooltip'
import { HowToRead } from '@/components/how-to-read'
import { MarketSummary } from '@/components/market-summary'
import { SiteHeader } from '@/components/site-header'
import { StockCard } from '@/components/stock-card'
import { TickerSearch } from '@/components/ticker-search'
import { analyzeBatch, ApiError } from '@/lib/api'
import { MAX_WATCHLIST, useWatchlist } from '@/lib/use-watchlist'
import type { SignalFailure, StockSignal } from '@/lib/types'

/** Prices refresh on this interval while the tab is visible. */
const REFRESH_MS = 120_000

interface LoadedState {
  /** Which ticker list these results correspond to. */
  key: string
  signals: StockSignal[]
  failures: SignalFailure[]
  at: Date
}

export function Dashboard() {
  const { tickers, add, remove, isFull } = useWatchlist()

  const [loaded, setLoaded] = useState<LoadedState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const tickersKey = tickers.join(',')

  // Results are only shown when they belong to the *current* ticker list.
  // Everything below is derived from that rather than stored, which keeps all
  // setState calls out of effect bodies — storing a `loading` flag means
  // setting it synchronously on mount, causing a cascading render.
  const current = loaded?.key === tickersKey ? loaded : null
  const loading = !error && tickers.length > 0 && current === null

  // Lets an in-flight request be cancelled so a slow response can never
  // overwrite newer state.
  const requestRef = useRef<AbortController | null>(null)

  const fetchSignals = useCallback(async (symbols: string[], key: string) => {
    requestRef.current?.abort()

    const controller = new AbortController()
    requestRef.current = controller

    try {
      const response = await analyzeBatch(symbols, 'fast', controller.signal)
      if (controller.signal.aborted) return
      setLoaded({ key, signals: response.signals, failures: response.failed, at: new Date() })
      setError(null)
    } catch (caught) {
      if (controller.signal.aborted) return
      setError(
        caught instanceof ApiError ? caught.message : 'Something went wrong loading your stocks.',
      )
    }
  }, [])

  // Fetch whenever the watchlist changes.
  useEffect(() => {
    // An empty watchlist needs no request; the empty state is derived above.
    if (!tickersKey) return

    // react-hooks/set-state-in-effect flags any call to a function that
    // contains setState, and cannot trace through an async boundary. Every
    // state update in fetchSignals happens *after* `await analyzeBatch(...)`,
    // so no cascading render occurs — which is the behaviour the rule exists
    // to prevent. Fetching on a dependency change is the documented pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchSignals(tickersKey.split(','), tickersKey)
  }, [tickersKey, fetchSignals])

  useEffect(() => () => requestRef.current?.abort(), [])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await fetchSignals(tickers, tickersKey)
    } finally {
      setRefreshing(false)
    }
  }, [fetchSignals, tickers, tickersKey])

  // Refresh on a timer, but only while the tab is visible — a background tab
  // polling every two minutes is wasted requests against a rate-limited API.
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible' && tickersKey) void refresh()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [refresh, tickersKey])

  const signals = current?.signals ?? []
  const failures = current?.failures ?? []

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen">
        <SiteHeader />

        <main className="mx-auto max-w-6xl space-y-6 px-4 py-8">
          <section className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Your stocks, explained
            </h1>
            <p className="text-muted-foreground max-w-2xl">
              We read the price chart and what people are saying, then tell you what it adds up
              to — in ordinary words, with the reasoning shown.
            </p>
          </section>

          <HowToRead />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <TickerSearch onSelect={add} existing={tickers} disabled={isFull} />

            <div className="flex items-center gap-3">
              {current && (
                <span className="text-muted-foreground text-xs">
                  Updated{' '}
                  {current.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => void refresh()}
                disabled={loading || refreshing || tickers.length === 0}
              >
                <RefreshCw className={refreshing ? 'animate-spin' : undefined} aria-hidden />
                Refresh
              </Button>
            </div>
          </div>

          {isFull && (
            <p className="text-muted-foreground text-xs">
              You are following the maximum of {MAX_WATCHLIST} stocks. Remove one to add another.
            </p>
          )}

          {error && (
            <Card className="border-negative/40 bg-negative-subtle gap-3 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="text-negative mt-0.5 size-4 shrink-0" aria-hidden />
                <div>
                  <p className="text-sm font-medium">We could not load your stocks</p>
                  <p className="text-muted-foreground mt-0.5 text-sm">{error}</p>
                  <Button variant="outline" size="sm" className="mt-3" onClick={() => void refresh()}>
                    Try again
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {failures.length > 0 && (
            <Card className="border-caution/40 bg-caution-subtle gap-2 p-4">
              <p className="text-sm font-medium">Some stocks could not be loaded</p>
              <ul className="text-muted-foreground space-y-1 text-sm">
                {failures.map((failure) => (
                  <li key={failure.ticker} className="flex items-center justify-between gap-3">
                    <span>
                      <span className="font-semibold">{failure.ticker}</span> — {failure.reason}
                    </span>
                    <Button variant="ghost" size="sm" onClick={() => remove(failure.ticker)}>
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {loading ? (
            <LoadingGrid />
          ) : signals.length > 0 ? (
            <>
              <MarketSummary signals={signals} />
              <div className="grid gap-4 md:grid-cols-2">
                {signals.map((signal) => (
                  <StockCard key={signal.ticker} signal={signal} onRemove={remove} />
                ))}
              </div>
            </>
          ) : (
            !error && <EmptyState />
          )}

          <footer className="border-border text-muted-foreground space-y-2 border-t pt-6 text-xs">
            <p className="font-medium">This is not financial advice.</p>
            <p className="max-w-3xl leading-relaxed">
              Quantimental summarises public price data and, where available, public news and
              social posts. It cannot predict the future, it does not know your circumstances,
              and it can be wrong. Do your own research and consider speaking to a licensed
              financial adviser before investing.
            </p>
          </footer>
        </main>
      </div>
    </TooltipProvider>
  )
}

function LoadingGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading your stocks…</span>
      {Array.from({ length: 4 }).map((_, index) => (
        <Card key={index} className="h-64 items-center justify-center p-5">
          <Loader2 className="text-muted-foreground size-5 animate-spin" aria-hidden />
        </Card>
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <Card className="items-center gap-2 p-10 text-center">
      <p className="font-medium">No stocks yet</p>
      <p className="text-muted-foreground max-w-sm text-sm">
        Search above to add your first one. Try a symbol like AAPL, or type a company name.
      </p>
    </Card>
  )
}
