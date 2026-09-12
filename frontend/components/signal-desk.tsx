'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { InfoTip } from '@/components/info-tip'
import { Sparkline } from '@/components/sparkline'
import { cn } from '@/lib/utils'
import { getSignalDesk } from '@/lib/api'
import type { MacroSignal, RiskTone, SignalDeskResponse } from '@/lib/types'

/** Macro moves slowly and the reading is identical for everyone. */
const REFRESH_MS = 5 * 60 * 1000

const TONE_TEXT: Record<RiskTone, string> = {
  risk_on: 'text-positive',
  risk_off: 'text-negative',
  neutral: 'text-muted-foreground',
}

/**
 * The Signal Desk: what moved across the whole market, how unusual it was,
 * and what it adds up to in one sentence.
 *
 * This is the front door of the product. A per-stock verdict answers "what
 * should I do", which requires being right about the future. This answers
 * "what is happening", which requires only being accurate about the present —
 * and it changes daily, so there is a reason to come back.
 */
export function SignalDesk() {
  const [data, setData] = useState<SignalDeskResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const requestRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller

    try {
      const response = await getSignalDesk(controller.signal)
      if (controller.signal.aborted) return
      setData(response)
      setFailed(false)
    } catch {
      if (controller.signal.aborted) return
      setFailed(true)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
    return () => requestRef.current?.abort()
  }, [load])

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [load])

  if (failed || (data && !data.available)) {
    return (
      <section className="border-border bg-card rounded-xl border p-4">
        <p className="text-muted-foreground flex items-center gap-2 text-sm">
          <AlertTriangle className="size-4 shrink-0" aria-hidden />
          {data && !data.available ? data.reason : 'Could not load market signals.'}
        </p>
      </section>
    )
  }

  if (!data) return <DeskSkeleton />

  const { signals, composite, sectors, history, narrative, lookback_days: lookback } = data

  return (
    <section
      aria-label="Market signal desk"
      className="border-border bg-card overflow-hidden rounded-xl border"
    >
      <header className="border-border flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="relative flex size-2" aria-hidden>
            <span className="bg-positive absolute inline-flex size-full animate-ping rounded-full opacity-60" />
            <span className="bg-positive relative inline-flex size-2 rounded-full" />
          </span>
          <h2 className="font-mono text-[11px] tracking-[0.2em] uppercase">Signal Desk</h2>
        </div>
        <span className="text-muted-foreground tabular font-mono text-[11px]">
          last {lookback} sessions
        </span>
      </header>

      <div className="grid lg:grid-cols-[1.15fr_1fr]">
        {/* Incoming signals */}
        <div className="border-border border-b p-4 lg:border-r lg:border-b-0">
          <p className="text-muted-foreground mb-3 flex items-center gap-1.5 font-mono text-[10px] tracking-[0.24em] uppercase">
            Incoming signals
            <InfoTip entry="sigma" />
          </p>
          <ul className="space-y-2.5">
            {signals.slice(0, 6).map((signal) => (
              <SignalRow key={signal.name} signal={signal} />
            ))}
          </ul>
        </div>

        {/* Composite + narrative */}
        <div className="flex flex-col p-4">
          <div className="flex items-baseline justify-between">
            <p className="text-muted-foreground flex items-center gap-1.5 font-mono text-[10px] tracking-[0.24em] uppercase">
              Risk appetite
              <InfoTip entry="riskAppetite" />
            </p>
            <span className={cn('tabular font-mono text-xs font-semibold', TONE_TEXT[composite.tone])}>
              {composite.label} · {composite.score}/100
            </span>
          </div>

          {history.length > 1 && (
            <div className="mt-3 h-16">
              <Sparkline data={history} height={64} />
            </div>
          )}

          {sectors.available && sectors.breadth !== null && (
            <p className="text-muted-foreground mt-3 text-xs">
              <span className="text-foreground font-medium">{sectors.breadth}%</span> of sectors
              advancing
              {sectors.leaders[0] && (
                <>
                  {' · '}
                  {sectors.leaders[0].name} leading
                </>
              )}
            </p>
          )}

          {narrative && (
            <div className="border-border mt-4 border-t pt-4">
              <p className="text-muted-foreground mb-2 font-mono text-[10px] tracking-[0.24em] uppercase">
                What it adds up to
              </p>
              <p className="text-sm leading-relaxed">{narrative.text}</p>
            </div>
          )}
        </div>
      </div>

      <footer className="border-border border-t px-4 py-2">
        <p className="text-muted-foreground font-mono text-[10px]">
          Describes market moves that have already happened. Not a forecast, not advice.
        </p>
      </footer>
    </section>
  )
}

const MARKS = { up: '▲', down: '▼', flat: '◆' } as const

function SignalRow({ signal }: { signal: MacroSignal }) {
  return (
    <li className="flex items-center gap-3 font-mono text-xs">
      <span className={cn('shrink-0', TONE_TEXT[signal.risk_tone])} aria-hidden>
        {MARKS[signal.direction]}
      </span>
      <span className="text-muted-foreground w-20 shrink-0 tracking-wide">{signal.category}</span>
      <span className="text-foreground/90 flex-1 truncate font-sans" title={signal.text}>
        {signal.text}
      </span>
      <span
        className={cn(
          'tabular shrink-0',
          signal.notable ? 'text-foreground font-semibold' : 'text-muted-foreground',
        )}
      >
        {signal.delta}
      </span>
    </li>
  )
}

function DeskSkeleton() {
  return (
    <section
      className="border-border bg-card h-64 animate-pulse rounded-xl border"
      aria-busy="true"
      aria-label="Loading market signals"
    />
  )
}
