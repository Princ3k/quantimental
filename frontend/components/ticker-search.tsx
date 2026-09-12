'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, Plus, Search } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { searchTickers } from '@/lib/api'
import type { SearchResult } from '@/lib/types'
import { cn } from '@/lib/utils'

interface TickerSearchProps {
  onSelect: (ticker: string) => void
  /** Already on the watchlist — shown as added rather than selectable. */
  existing: string[]
  disabled?: boolean
}

const DEBOUNCE_MS = 250

/**
 * Search box backed by the live ticker search endpoint.
 *
 * Replaces a hard-coded array of eight companies with real lookup, and shows
 * curated suggestions on focus so the empty state is still useful.
 */
export function TickerSearch({ onSelect, existing, disabled }: TickerSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const controller = new AbortController()
    // Debounced so typing "NVDA" issues one request, not four.
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const response = await searchTickers(query, controller.signal)
        setResults(response.results)
      } catch {
        // A failed lookup shows nothing rather than an error dialog; the user
        // can still type a symbol and press Enter.
        setResults([])
      } finally {
        setLoading(false)
      }
    }, DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, open])

  // Close the dropdown on an outside click.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const choose = (ticker: string) => {
    onSelect(ticker)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && query.trim()) choose(query.trim().toUpperCase())
            if (event.key === 'Escape') setOpen(false)
          }}
          disabled={disabled}
          placeholder="Add a stock — try AAPL or Tesla"
          aria-label="Search for a stock to add to your list"
          className="pl-9"
        />
        {loading && (
          <Loader2
            className="text-muted-foreground absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin"
            aria-hidden
          />
        )}
      </div>

      {open && results.length > 0 && (
        <ul className="bg-popover border-border absolute z-50 mt-2 max-h-72 w-full overflow-auto rounded-lg border p-1 shadow-lg">
          {!query && (
            <li className="text-muted-foreground px-3 py-1.5 text-xs font-medium">
              Popular stocks
            </li>
          )}
          {results.map((result) => {
            const added = existing.includes(result.ticker.toUpperCase())
            return (
              <li key={result.ticker}>
                <button
                  type="button"
                  onClick={() => !added && choose(result.ticker)}
                  disabled={added}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors',
                    added ? 'cursor-default opacity-50' : 'hover:bg-accent',
                  )}
                >
                  <span className="min-w-0">
                    <span className="font-semibold">{result.ticker}</span>
                    <span className="text-muted-foreground ml-2 truncate text-xs">
                      {result.name}
                    </span>
                  </span>
                  {added ? (
                    <span className="text-muted-foreground shrink-0 text-xs">Added</span>
                  ) : (
                    <Plus className="text-muted-foreground size-4 shrink-0" aria-hidden />
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
