'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { Sparkline } from '@/components/sparkline'
import { cn } from '@/lib/utils'
import { getSignalDesk } from '@/lib/api'
import type { MacroSignal, RiskTone, SignalDeskResponse } from '@/lib/types'

const REFRESH_MS = 5 * 60 * 1000

const TONE: Record<RiskTone, string> = {
  risk_on: 'text-up',
  risk_off: 'text-down',
  neutral: 'text-ink-3',
}

/**
 * The market-wide read: what moved, how unusual it was, what it adds up to.
 *
 * This is the front door. It describes what has already happened, which the
 * engine can do accurately, rather than predicting, which a backtest says it
 * cannot. It also changes daily and needs no setup, so it is useful before a
 * visitor has added a single stock.
 */
export function SignalDesk({ note }: { note?: string | null }) {
  const [data, setData] = useState<SignalDeskResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const request = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    try {
      const response = await getSignalDesk(controller.signal)
      if (controller.signal.aborted) return
      setData(response)
      setFailed(false)
    } catch {
      if (!controller.signal.aborted) setFailed(true)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
    return () => request.current?.abort()
  }, [load])

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [load])

  if (failed || (data && !data.available)) {
    return (
      <p className="text-ink-3 text-sm">
        {data && !data.available ? data.reason : 'Market signals are unavailable right now.'}
      </p>
    )
  }

  if (!data) {
    return <div className="bg-rule/40 h-44 animate-pulse rounded-lg" aria-label="Loading" />
  }


  const { signals, composite, sectors, history, narrative, context } = data

  return (
    <section aria-label="Market overview">
      {/* The sentence leads. Everything below is the evidence for it. */}
      <p className="max-w-2xl text-lg leading-snug text-balance sm:text-xl">{narrative?.text}</p>

      {context && <p className="text-ink-3 mt-2.5 max-w-2xl text-sm">{context}</p>}

      {note && <p className="mt-2.5 max-w-2xl text-sm">{note}</p>}

      <div className="mt-7 grid gap-x-10 gap-y-7 sm:grid-cols-[1fr_auto]">
        {/* What moved */}
        <div>
          <p className="eyebrow mb-3">What moved this week</p>
          <ul className="space-y-2">
            {signals.slice(0, 5).map((signal) => (
              <Row key={signal.name} signal={signal} />
            ))}
          </ul>
        </div>

        {/* Risk appetite */}
        <div className="sm:w-44">
          <p className="eyebrow mb-3">Risk appetite</p>
          <p className={cn('tnum font-mono text-2xl leading-none font-medium', TONE[composite.tone])}>
            {composite.score}
            <span className="text-ink-3 text-sm font-normal"> / 100</span>
          </p>
          <p className="text-ink-2 mt-1.5 text-[0.8125rem]">{composite.label}</p>
          {history.length > 1 && (
            <div className="mt-3">
              <Sparkline data={history} height={34} />
            </div>
          )}
          {sectors.available && sectors.breadth !== null && (
            <p className="text-ink-3 tnum mt-3 text-[0.8125rem] leading-relaxed">
              {sectors.breadth}% of sectors rising
              {sectors.leaders[0] && <>, {sectors.leaders[0].name} leading</>}
            </p>
          )}
        </div>
      </div>

      <p className="text-ink-3 mt-6 text-xs leading-relaxed">
        Describes moves that have already happened. Not a forecast, not advice.
      </p>
    </section>
  )
}

const MARK = { up: '↑', down: '↓', flat: '·' } as const

function Row({ signal }: { signal: MacroSignal }) {
  return (
    <li className="flex items-baseline gap-3 text-sm">
      <span className={cn('w-3 shrink-0 font-mono', TONE[signal.risk_tone])} aria-hidden>
        {MARK[signal.direction]}
      </span>
      <span className="text-ink-2 flex-1 leading-snug">{signal.text}</span>
      <span
        className={cn(
          'tnum shrink-0 font-mono text-[0.8125rem]',
          signal.notable ? 'text-ink' : 'text-ink-3',
        )}
      >
        {signal.delta}
      </span>
    </li>
  )
}
