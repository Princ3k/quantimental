'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'

import { analyzeBatch, searchTickers } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { SearchResult, StockSignal } from '@/lib/types'
import { trackSearch } from '@/lib/events'

const DEBOUNCE_MS = 250

type Preview =
  | { state: 'loading'; ticker: string }
  | { state: 'ready'; ticker: string; signal: StockSignal }
  | { state: 'failed'; ticker: string; reason: string }

/**
 * Find a stock, look at it, then decide.
 *
 * Searching used to add. Clicking a result put the stock straight into the
 * watchlist, which made the search box a commitment rather than a question —
 * and pressing Enter added whatever had been typed, so "nvidia" became a
 * holding called NVIDIA that sat there failing until someone removed it by
 * hand. Nothing can be added here now without first resolving to a real
 * instrument and showing what it is.
 */
export function TickerSearch({
  onAdd,
  existing,
  addDisabled,
}: {
  onAdd: (ticker: string) => void
  existing: string[]
  /** The watchlist is full. Looking is still allowed; only following is not. */
  addDisabled?: boolean
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const container = useRef<HTMLDivElement>(null)
  const previewRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    // Debounced so typing "NVDA" issues one request, not four.
    const timer = setTimeout(async () => {
      try {
        setResults((await searchTickers(query, controller.signal)).results)
      } catch {
        setResults([])
      }
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!container.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  useEffect(() => () => previewRequest.current?.abort(), [])

  /** Fetch one stock so the person can see it before choosing to follow it. */
  const show = useCallback(async (ticker: string) => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return

    trackSearch(symbol)
    previewRequest.current?.abort()
    const controller = new AbortController()
    previewRequest.current = controller

    setQuery('')
    setOpen(false)
    setResults([])
    setPreview({ state: 'loading', ticker: symbol })

    try {
      // The batch path at `fast` depth, which is what the cards themselves
      // use — so the preview shows the same reading the stock will show once
      // followed, and an unknown symbol comes back as data in `failed` rather
      // than as an exception. analyzeStock would run the whole sentiment
      // pipeline to render two lines.
      const response = await analyzeBatch([symbol], 'fast', controller.signal)
      if (controller.signal.aborted) return

      const signal = response.signals[0]
      if (signal) {
        setPreview({ state: 'ready', ticker: symbol, signal })
        return
      }
      setPreview({
        state: 'failed',
        ticker: symbol,
        reason:
          response.failed[0]?.reason ?? `No market data available for ${symbol}.`,
      })
    } catch {
      if (controller.signal.aborted) return
      setPreview({
        state: 'failed',
        ticker: symbol,
        reason: `Could not reach our market data just now. Try ${symbol} again shortly.`,
      })
    }
  }, [])

  const dismiss = useCallback(() => {
    previewRequest.current?.abort()
    setPreview(null)
  }, [])

  const confirm = useCallback(
    (ticker: string) => {
      onAdd(ticker)
      setPreview(null)
    },
    [onAdd],
  )

  const alreadyFollowing = preview ? existing.includes(preview.ticker) : false

  return (
    <div ref={container} className="relative w-full max-w-xs">
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          // Opening here, not only on focus. `show` closes the list while the
          // input keeps focus, so a search box that reopened only on focus
          // stayed shut for every subsequent search — it accepted typing and
          // never looked anything up again, which read as the page freezing.
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && query.trim()) {
            // The first result, not the raw text — otherwise "nvidia" resolves
            // to a holding named NVIDIA. With nothing matched, the typed
            // symbol is still looked up, and an unknown one fails in the
            // preview instead of silently entering the watchlist.
            void show(results[0]?.ticker ?? query.trim())
          }
          if (e.key === 'Escape') setOpen(false)
        }}
        placeholder="Search a stock"
        aria-label="Search for a stock"
        className="border-rule placeholder:text-ink-3 focus:border-rule-strong w-full border-b bg-transparent pb-1.5 text-sm outline-none transition-colors disabled:opacity-40"
      />

      {open && results.length > 0 && (
        <ul className="border-rule bg-surface absolute z-50 mt-2 max-h-72 w-full overflow-auto rounded-md border py-1 shadow-lg">
          {!query && <li className="eyebrow px-3 py-1.5">Popular</li>}
          {results.map((result) => {
            const added = existing.includes(result.ticker.toUpperCase())
            return (
              <li key={result.ticker} className="flex items-baseline">
                {/* Selecting shows the stock; it no longer follows it. A row
                    already followed stays clickable, because a dead row that
                    swallows the click is the thing people report as broken. */}
                <button
                  type="button"
                  onClick={() => void show(result.ticker)}
                  className="hover:bg-rule/40 flex min-w-0 flex-1 items-baseline gap-2.5 px-3 py-1.5 text-left text-sm transition-colors"
                >
                  <span className="font-mono text-[0.8125rem] font-medium">{result.ticker}</span>
                  <span className="text-ink-3 flex-1 truncate text-[0.8125rem]">{result.name}</span>
                  {added && <span className="text-ink-3 text-xs">following</span>}
                </button>
                <Link
                  href={`/stock/${result.ticker.toLowerCase()}`}
                  className="text-ink-3 hover:text-ink px-2.5 py-1.5 text-xs transition-colors"
                  aria-label={`Open the ${result.ticker} page`}
                >
                  Page →
                </Link>
              </li>
            )
          })}
        </ul>
      )}

      {preview && (
        <div className="border-rule bg-surface absolute z-40 mt-2 w-full rounded-md border p-3.5 shadow-lg">
          {preview.state === 'loading' && (
            <p className="text-ink-3 text-[0.8125rem]">Looking up {preview.ticker}…</p>
          )}

          {preview.state === 'failed' && (
            <>
              <p className="text-ink-2 text-[0.8125rem] leading-relaxed">{preview.reason}</p>
              <button
                type="button"
                onClick={dismiss}
                className="text-ink-3 hover:text-ink mt-2.5 text-[0.8125rem] transition-colors"
              >
                Close
              </button>
            </>
          )}

          {preview.state === 'ready' && (
            <>
              <div className="flex items-baseline gap-2.5">
                <span className="font-mono text-[0.8125rem] font-medium">{preview.signal.ticker}</span>
                <span className="text-ink-3 flex-1 truncate text-[0.8125rem]">
                  {preview.signal.company_name}
                </span>
              </div>
              <div className="tnum mt-1.5 flex items-baseline gap-3 text-[0.8125rem]">
                <span>
                  {preview.signal.price.toLocaleString(undefined, {
                    style: 'currency',
                    currency: 'USD',
                  })}
                </span>
                <span
                  className={cn(
                    preview.signal.change_percent > 0 && 'text-up',
                    preview.signal.change_percent < 0 && 'text-down',
                    preview.signal.change_percent === 0 && 'text-ink-3',
                  )}
                >
                  {preview.signal.change_percent > 0 ? '↑' : preview.signal.change_percent < 0 ? '↓' : ''}{' '}
                  {Math.abs(preview.signal.change_percent).toFixed(2)}% today
                </span>
              </div>
              <p className="text-ink-2 mt-2 text-[0.8125rem] leading-relaxed text-balance">
                {preview.signal.situation.headline}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-4">
                {alreadyFollowing ? (
                  <span className="text-ink-3 text-[0.8125rem]">
                    Already in your stocks.
                  </span>
                ) : addDisabled ? (
                  <span className="text-ink-3 text-[0.8125rem]">
                    Your list is full — remove one to follow this.
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => confirm(preview.signal.ticker)}
                    className="hover:text-ink text-[0.8125rem] underline underline-offset-4 transition-colors disabled:opacity-40"
                  >
                    Add to your stocks
                  </button>
                )}
                <Link
                  href={`/stock/${preview.signal.ticker.toLowerCase()}`}
                  className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors"
                >
                  Full page →
                </Link>
                <button
                  type="button"
                  onClick={dismiss}
                  className="text-ink-3 hover:text-ink ml-auto text-[0.8125rem] transition-colors"
                >
                  Close
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
