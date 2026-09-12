'use client'

import { useEffect, useRef, useState } from 'react'

import { searchTickers } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { SearchResult } from '@/lib/types'

const DEBOUNCE_MS = 250

export function TickerSearch({
  onSelect,
  existing,
  disabled,
}: {
  onSelect: (ticker: string) => void
  existing: string[]
  disabled?: boolean
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)

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

  const choose = (ticker: string) => {
    onSelect(ticker)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={container} className="relative w-full max-w-xs">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && query.trim()) choose(query.trim().toUpperCase())
          if (e.key === 'Escape') setOpen(false)
        }}
        disabled={disabled}
        placeholder="Add a stock"
        aria-label="Search for a stock"
        className="border-rule placeholder:text-ink-3 focus:border-rule-strong w-full border-b bg-transparent pb-1.5 text-sm outline-none transition-colors disabled:opacity-40"
      />

      {open && results.length > 0 && (
        <ul className="border-rule bg-surface absolute z-50 mt-2 max-h-72 w-full overflow-auto rounded-md border py-1 shadow-lg">
          {!query && <li className="eyebrow px-3 py-1.5">Popular</li>}
          {results.map((result) => {
            const added = existing.includes(result.ticker.toUpperCase())
            return (
              <li key={result.ticker}>
                <button
                  type="button"
                  onClick={() => !added && choose(result.ticker)}
                  disabled={added}
                  className={cn(
                    'flex w-full items-baseline gap-2.5 px-3 py-1.5 text-left text-sm transition-colors',
                    added ? 'cursor-default opacity-35' : 'hover:bg-rule/40',
                  )}
                >
                  <span className="font-mono text-[0.8125rem] font-medium">{result.ticker}</span>
                  <span className="text-ink-3 flex-1 truncate text-[0.8125rem]">{result.name}</span>
                  {added && <span className="text-ink-3 text-xs">added</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
