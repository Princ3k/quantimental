'use client'

import { useState } from 'react'

import { analyzeDeep, ApiError } from '@/lib/api'
import { trackDeepDive } from '@/lib/events'
import type { StockSignal } from '@/lib/types'

/**
 * Runs the full pipeline for one stock, on demand.
 *
 * The dashboard loads a dozen stocks at `fast` depth, which skips sentiment
 * entirely — so the Psych engine, the ML models and the Reddit/news/Twitter
 * fetchers never execute in production. Half of what the product claims to do
 * was built and then never reached.
 *
 * It stays on demand rather than automatic because it costs several seconds
 * and real API quota per stock. A user asking about one company is worth that;
 * twelve cards loading it on sight is not.
 */
export function DeepDive({
  ticker,
  onResult,
}: {
  ticker: string
  onResult: (signal: StockSignal) => void
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [message, setMessage] = useState<string | null>(null)

  const run = async () => {
    trackDeepDive(ticker)
    setState('loading')
    setMessage(null)
    try {
      onResult(await analyzeDeep(ticker))
      setState('idle')
    } catch (error) {
      setState('error')
      setMessage(
        error instanceof ApiError ? error.message : 'Could not complete the analysis.',
      )
    }
  }

  if (state === 'error') {
    return (
      <div className="text-[0.8125rem]">
        <p className="text-down">{message}</p>
        <button
          type="button"
          onClick={() => void run()}
          className="text-ink-3 hover:text-ink mt-1 transition-colors"
        >
          Try again
        </button>
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => void run()}
      disabled={state === 'loading'}
      className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors disabled:opacity-60"
    >
      {state === 'loading' ? 'Reading the news…' : 'Add news & social sentiment'}
      {state !== 'loading' && <span aria-hidden className="ml-1">→</span>}
    </button>
  )
}
