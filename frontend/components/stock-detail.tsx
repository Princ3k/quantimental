'use client'

import { useEffect, useState } from 'react'

import { DeepDive } from '@/components/deep-dive'
import { Sparkline } from '@/components/sparkline'
import { analyzeStock, ApiError } from '@/lib/api'
import { useWatchlist } from '@/lib/use-watchlist'
import type { StockSignal } from '@/lib/types'

/**
 * The live half of a stock page.
 *
 * The page above this renders from the static snapshot, so it is complete and
 * indexable before any script runs. This fills in what the snapshot cannot
 * carry — the chart, the indicator notes, the news — by calling the API once,
 * from the browser.
 *
 * Splitting it this way is deliberate: crawlers and link previews get the
 * static half and never reach our server, so 503 indexable pages cost nothing
 * in API load.
 */
export function StockDetail({ ticker }: { ticker: string }) {
  const [signal, setSignal] = useState<StockSignal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const { tickers, add, isFull } = useWatchlist()

  // The watchlist lives in localStorage, which the server cannot read — so
  // during prerender the hook returns the default list, and rendering from it
  // would bake "You're following AAPL" into static HTML served to everyone,
  // including people who follow nothing. The follow control stays absent until
  // the browser can answer the question.
  useEffect(() => setHydrated(true), [])

  const following = hydrated && tickers.includes(ticker)

  useEffect(() => {
    const controller = new AbortController()
    analyzeStock(ticker, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setSignal(result)
      })
      .catch((caught) => {
        if (controller.signal.aborted) return
        setError(caught instanceof ApiError ? caught.message : 'Could not load live data.')
      })
    return () => controller.abort()
  }, [ticker])

  return (
    <div className="mt-10 space-y-8">
      {hydrated &&
        (following ? (
          <p className="text-ink-3 text-[0.8125rem]">You&rsquo;re following {ticker}.</p>
        ) : (
          !isFull && (
            <button
              type="button"
              onClick={() => add(ticker)}
              className="border-rule hover:border-rule-strong rounded-md border px-3.5 py-2 text-[0.8125rem] transition-colors"
            >
              Follow {ticker}
            </button>
          )
        ))}

      {error && <p className="text-ink-3 text-[0.8125rem]">{error}</p>}

      {!signal && !error && (
        <div className="bg-rule/40 h-28 animate-pulse rounded-lg" aria-busy="true" />
      )}

      {signal && (
        <>
          {signal.price_history.length > 1 && (
            <div>
              <p className="eyebrow mb-3">Past year</p>
              <Sparkline data={signal.price_history} height={72} />
            </div>
          )}

          {signal.situation.notable.length > 0 && (
            <ul className="space-y-2">
              {signal.situation.notable.map((note) => (
                <li
                  key={note}
                  className="text-ink-2 border-rule-strong border-l-2 pl-3 text-[0.875rem] leading-relaxed"
                >
                  {note}
                </li>
              ))}
            </ul>
          )}

          {signal.technical_analysis.notes.length > 0 && (
            <div>
              <p className="eyebrow mb-3">What the chart shows</p>
              <ul className="space-y-2">
                {signal.technical_analysis.notes.map((note) => (
                  <li key={note} className="text-ink-2 text-[0.875rem] leading-relaxed">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {signal.sentiment_analysis.available ? (
            <NewsList signal={signal} />
          ) : (
            <DeepDive ticker={ticker} onResult={setSignal} />
          )}
        </>
      )}
    </div>
  )
}

function NewsList({ signal }: { signal: StockSignal }) {
  const headlines = signal.sentiment_analysis.headlines ?? []
  if (headlines.length === 0) return null

  return (
    <div>
      <p className="eyebrow mb-3">What we read</p>
      <ul className="space-y-3">
        {headlines.map((item) => (
          <li key={item.url || item.title}>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink-2 hover:text-ink text-[0.875rem] leading-relaxed transition-colors"
            >
              {item.title}
            </a>
            {item.source && (
              <span className="text-ink-3 ml-1.5 text-[0.75rem]">{item.source}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
