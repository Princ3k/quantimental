'use client'

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'

import { getPriceHistory, type PricePoint, type PriceRange } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * A price chart you can actually read.
 *
 * The card sparklines are decorative and aria-hidden: a shape beside a number.
 * On a stock page that is a wasted half-screen, because the whole product is
 * about what happened — and "what happened" needs dates on it.
 *
 * So this one answers questions. Hover or drag for the close on any session,
 * switch the window, and read the range off the axis. Pointer events rather
 * than mouse events, so a touchscreen gets the same readout; keyboard arrows
 * walk the series for anyone not using a pointer at all.
 */

const RANGES: { value: PriceRange; label: string }[] = [
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: '6m', label: '6M' },
  { value: '1y', label: '1Y' },
]

interface Loaded {
  /** The `ticker|range` this data answered, so a stale response is ignored. */
  key: string
  points: PricePoint[] | null
  failed: boolean
}

const HEIGHT = 200
const PAD_TOP = 12
const PAD_BOTTOM = 22

export function PriceChart({ ticker }: { ticker: string }) {
  const [range, setRange] = useState<PriceRange>('1y')
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [hovered, setHovered] = useState<number | null>(null)

  const gradientId = useId()
  const svgRef = useRef<SVGSVGElement>(null)

  const key = `${ticker}|${range}`

  /*
   * Derived, not reset in an effect.
   *
   * Switching range must clear the previous series, and the obvious way to do
   * that — setState at the top of the effect — schedules an extra render on
   * every change and is what React's lint rules reject. Tagging the fetched
   * data with the request that produced it means stale results are simply not
   * shown, with no reset to perform. The dashboard keys its loaded state the
   * same way.
   */
  const current = loaded?.key === key ? loaded : null
  const points = current?.points ?? null
  const failed = current?.failed ?? false

  // An index into a series that has since changed would read the wrong bar.
  const active =
    points && hovered !== null ? Math.min(hovered, points.length - 1) : null

  useEffect(() => {
    const controller = new AbortController()

    getPriceHistory(ticker, range, controller.signal)
      .then((history) => {
        if (controller.signal.aborted) return
        setLoaded(
          history.available && history.points?.length
            ? { key: `${ticker}|${range}`, points: history.points, failed: false }
            : { key: `${ticker}|${range}`, points: null, failed: true },
        )
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setLoaded({ key: `${ticker}|${range}`, points: null, failed: true })
      })

    return () => controller.abort()
  }, [ticker, range])

  const geometry = useMemo(() => {
    if (!points || points.length < 2) return null

    const closes = points.map((p) => p.c)
    const min = Math.min(...closes)
    const max = Math.max(...closes)
    const span = max - min || 1

    const x = (i: number) => (i / (points.length - 1)) * 1000
    const y = (value: number) =>
      HEIGHT - PAD_BOTTOM - ((value - min) / span) * (HEIGHT - PAD_TOP - PAD_BOTTOM)

    const line = points
      .map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.c).toFixed(1)}`)
      .join('')

    return {
      min,
      max,
      x,
      y,
      line,
      area: `${line}L1000,${HEIGHT - PAD_BOTTOM}L0,${HEIGHT - PAD_BOTTOM}Z`,
      rising: closes[closes.length - 1] >= closes[0],
    }
  }, [points])

  /** Nearest session to a pointer position, in the SVG's own coordinates. */
  const pick = useCallback(
    (clientX: number) => {
      const svg = svgRef.current
      if (!svg || !points) return
      const box = svg.getBoundingClientRect()
      if (box.width === 0) return
      const ratio = (clientX - box.left) / box.width
      const index = Math.round(ratio * (points.length - 1))
      setHovered(Math.max(0, Math.min(points.length - 1, index)))
    },
    [points],
  )

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!points) return
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const step = event.key === 'ArrowRight' ? 1 : -1
    setHovered((previous) => {
      const next = (previous ?? points.length - 1) + step
      return Math.max(0, Math.min(points.length - 1, next))
    })
  }

  const shown = points && active !== null ? points[active] : points?.[points.length - 1]
  const stroke = geometry?.rising ? 'var(--up)' : 'var(--down)'

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 items-baseline gap-3">
          <p className="eyebrow">Price</p>
          {/* Shares the header row with the eyebrow rather than floating above
              the chart, where it collided with the range buttons. Fixed width
              so the buttons do not shift as the value changes under the
              cursor. */}
          <p className="tnum min-w-0 font-mono text-[0.8125rem]">
            {shown && (
              <>
                <span className="text-ink">${shown.c.toFixed(2)}</span>
                <span className="text-ink-3 ml-2 hidden sm:inline">{formatDate(shown.d)}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 gap-1" role="group" aria-label="Chart range">
          {RANGES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setRange(option.value)}
              aria-pressed={range === option.value}
              className={cn(
                'tnum rounded px-2 py-1 font-mono text-[0.6875rem] transition-colors',
                range === option.value
                  ? 'bg-rule text-ink'
                  : 'text-ink-3 hover:text-ink',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Reserved height, so switching range does not make the page jump. */}
      <div className="relative mt-3" style={{ height: HEIGHT }}>
        {!points && !failed && (
          <div className="bg-rule/40 h-full animate-pulse rounded" aria-busy="true" />
        )}

        {failed && !points && (
          <p className="text-ink-3 pt-8 text-[0.8125rem]">Price history is unavailable.</p>
        )}

        {geometry && points && (
          <>
            <svg
              ref={svgRef}
              viewBox={`0 0 1000 ${HEIGHT}`}
              preserveAspectRatio="none"
              className="h-full w-full touch-none outline-none"
              role="img"
              aria-label={`${ticker} closing price, ${formatDate(points[0].d)} to ${formatDate(points[points.length - 1].d)}`}
              tabIndex={0}
              onKeyDown={onKeyDown}
              onPointerMove={(e) => pick(e.clientX)}
              onPointerDown={(e) => pick(e.clientX)}
              onPointerLeave={() => setHovered(null)}
              onBlur={() => setHovered(null)}
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity="0.16" />
                  <stop offset="100%" stopColor={stroke} stopOpacity="0" />
                </linearGradient>
              </defs>

              <path d={geometry.area} fill={`url(#${gradientId})`} />
              <path
                d={geometry.line}
                fill="none"
                stroke={stroke}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                strokeLinecap="round"
              />

              {active !== null && (
                <g>
                  <line
                    x1={geometry.x(active)}
                    x2={geometry.x(active)}
                    y1={PAD_TOP}
                    y2={HEIGHT - PAD_BOTTOM}
                    stroke="var(--rule-strong)"
                    strokeWidth="1"
                    vectorEffect="non-scaling-stroke"
                  />
                  <circle
                    cx={geometry.x(active)}
                    cy={geometry.y(points[active].c)}
                    r="3"
                    fill={stroke}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              )}
            </svg>

            {/* High and low as text, not gridlines. Two numbers answer "what
                range is this?" without drawing a lattice over the shape. */}
            <div className="text-ink-3 tnum pointer-events-none absolute inset-x-0 top-0 flex justify-between font-mono text-[0.6875rem]">
              <span>{formatDate(points[0].d)}</span>
              <span>high ${geometry.max.toFixed(2)}</span>
            </div>
            <div className="text-ink-3 tnum pointer-events-none absolute inset-x-0 bottom-0 flex justify-between font-mono text-[0.6875rem]">
              <span>{formatDate(points[points.length - 1].d)}</span>
              <span>low ${geometry.min.toFixed(2)}</span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}
