'use client'

import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'
import { getUnusualScan, type UnusualMove, type UnusualScan } from '@/lib/unusual'

/**
 * What moved unusually across the S&P 500 today.
 *
 * The reason to open this on a day when your own six stocks did nothing. A
 * watchlist is quiet most days, and an app with nothing to say is an app
 * nobody comes back to — so this scans 503 stocks and reports the ones having
 * a genuinely odd session.
 *
 * "Genuinely" is doing real work there. These are ranked by how far the move
 * sits outside *that stock's own* normal daily range, not by raw percentage. A
 * percentage leaderboard is the same handful of volatile tickers every day,
 * which is not news and would not be worth returning for.
 *
 * On a calm day nothing clears the bar. Rather than pad the list, the panel
 * says so and shows the day's biggest moves under a heading that makes the
 * weaker claim — "biggest" and "unusual" are different statements and blurring
 * them is how a tool stops being trustworthy.
 */
export function UnusualFeed({ onPick }: { onPick?: (ticker: string) => void }) {
  const [scan, setScan] = useState<UnusualScan | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void getUnusualScan(controller.signal).then((result) => {
      if (!controller.signal.aborted) setScan(result)
    })
    return () => controller.abort()
  }, [])

  // A missing scan removes the panel rather than showing an error. Nobody came
  // to the page for this section.
  if (!scan) return null

  const unusual = scan.movers.length > 0
  const shown = unusual ? scan.movers : scan.biggest
  const visible = expanded ? shown : shown.slice(0, 5)

  return (
    <section className="rule-t pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-[0.9375rem] font-medium">
          {unusual
            ? `${scan.unusual_count} ${scan.unusual_count === 1 ? 'stock is' : 'stocks are'} having an unusual day`
            : 'A calm day across the market'}
        </h2>
        <p className="text-ink-3 text-[0.8125rem]">
          {scan.scanned.toLocaleString()} stocks scanned
          {scan.as_of && ` · ${formatSession(scan.as_of)}`}
        </p>
      </div>

      <p className="text-ink-3 mt-1.5 text-[0.8125rem] leading-relaxed">
        {unusual
          ? `Moves at least ${scan.threshold.multiple}× larger than that stock's own typical day.`
          : `Nothing moved more than ${scan.threshold.multiple}× its normal range. These were the day's biggest moves.`}
      </p>

      <ul className="mt-4 space-y-2.5">
        {visible.map((move) => (
          <MoveRow key={move.ticker} move={move} onPick={onPick} showMultiple={unusual} />
        ))}
      </ul>

      {shown.length > 5 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-ink-3 hover:text-ink mt-3 text-[0.8125rem] transition-colors"
        >
          {expanded ? 'Show fewer' : `Show all ${shown.length}`}
          <span aria-hidden className="ml-1">{expanded ? '↑' : '↓'}</span>
        </button>
      )}
    </section>
  )
}

function MoveRow({
  move,
  onPick,
  showMultiple,
}: {
  move: UnusualMove
  onPick?: (ticker: string) => void
  showMultiple: boolean
}) {
  const up = move.direction === 'up'

  const body = (
    <>
      <span className="font-mono text-[0.8125rem]">{move.ticker}</span>
      <span className="text-ink-2 min-w-0 flex-1 truncate text-[0.8125rem]">{move.company}</span>
      {showMultiple && (
        <span className="text-ink-3 tnum shrink-0 text-[0.75rem]">
          {move.multiple.toFixed(1)}× normal
        </span>
      )}
      <span className={cn('tnum shrink-0 text-[0.8125rem]', up ? 'text-up' : 'text-down')}>
        {up ? '↑' : '↓'} {Math.abs(move.change_percent).toFixed(1)}%
      </span>
    </>
  )

  if (!onPick) {
    return <li className="flex items-baseline gap-3">{body}</li>
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => onPick(move.ticker)}
        title={move.headline}
        className="hover:bg-surface -mx-2 flex w-[calc(100%+1rem)] items-baseline gap-3 rounded px-2 py-1 text-left transition-colors"
      >
        {body}
      </button>
    </li>
  )
}

/** "Friday's close" reads better than a date, and says what it is. */
function formatSession(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return iso

  const today = new Date()
  const isToday = date.toISOString().slice(0, 10) === today.toISOString().slice(0, 10)
  if (isToday) return 'today'

  return `${date.toLocaleDateString(undefined, { weekday: 'long', timeZone: 'UTC' })}'s close`
}
