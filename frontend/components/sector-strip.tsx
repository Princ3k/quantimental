'use client'

import Link from 'next/link'

import { cn } from '@/lib/utils'
import type { SectorSummaryRow } from '@/lib/sectors'

/**
 * Every sector, ranked.
 *
 * The desk already says "30% of sectors rising, Energy leading" and then
 * leaves the obvious question — *which* sectors? — unanswered. This is the
 * answer, and it is also the route into the sector pages.
 *
 * `compact` shows only the strongest and weakest three. On the dashboard,
 * eleven rows of medians is reference data competing with the thing the
 * reader actually came for; the full list belongs on the sector pages, where
 * someone has already chosen to look.
 *
 * Bars are scaled to the largest move on the day rather than a fixed
 * percentage, so the shape shows relative strength on *this* day instead of
 * flattening to nothing on a quiet one. They are deliberately not a chart: no
 * axis, no ticks, just enough length to rank at a glance before the number
 * beside them gives the exact figure.
 */
export function SectorStrip({
  sectors,
  compact = false,
}: {
  sectors: SectorSummaryRow[]
  /** Show only the extremes. Eleven medians is reference data, not a glance. */
  compact?: boolean
}) {
  if (sectors.length === 0) return null

  // Scaled against the full set even when only the extremes are shown, so a
  // bar means the same thing in both modes.
  const widest = Math.max(...sectors.map((s) => Math.abs(s.change_percent)), 0.1)

  const ENDS = 3
  const trimmed = compact && sectors.length > ENDS * 2
  const shown = trimmed
    ? [...sectors.slice(0, ENDS), ...sectors.slice(-ENDS)]
    : sectors
  const hidden = sectors.length - shown.length

  return (
    <section className={compact ? '' : 'rule-t py-10 sm:py-12'}>
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="eyebrow">{compact ? 'Sectors' : 'All sectors'}</p>
        <p className="text-ink-3 text-[0.8125rem]">
          median move · how many rose
        </p>
      </div>

      {/* Two columns only once there is room for a full sector name beside
          its bar and figures. At the `sm` breakpoint each column was ~280px
          and "Consumer Discretionary" truncated to "Consumer Discreti...". */}
      <ul className="grid gap-x-10 gap-y-1 lg:grid-cols-2">
        {shown.map((sector) => (
          <li key={sector.slug}>
            <Link
              href={`/sector/${sector.slug}`}
              className="hover:bg-surface -mx-2 flex items-center gap-3 rounded px-2 py-2 transition-colors"
            >
              <span className="min-w-0 flex-1 text-[0.875rem]">{sector.name}</span>

              {/* Centre line with the bar growing either side, so direction
                  reads before the number does. */}
              <span className="relative hidden h-1.5 w-20 shrink-0 sm:block" aria-hidden>
                <span className="bg-rule absolute inset-y-0 left-1/2 w-px" />
                <span
                  className={cn(
                    'absolute inset-y-0 rounded-sm',
                    sector.change_percent >= 0 ? 'bg-up left-1/2' : 'bg-down right-1/2',
                  )}
                  style={{
                    width: `${(Math.abs(sector.change_percent) / widest) * 50}%`,
                  }}
                />
              </span>

              <span className="text-ink-3 tnum hidden w-16 shrink-0 text-right font-mono text-[0.6875rem] sm:block">
                {sector.rising}/{sector.members}
              </span>

              <span
                className={cn(
                  'tnum w-16 shrink-0 text-right font-mono text-[0.8125rem]',
                  sector.change_percent >= 0 ? 'text-up' : 'text-down',
                )}
              >
                {sector.change_percent >= 0 ? '+' : ''}
                {sector.change_percent.toFixed(2)}%
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {trimmed && (
        <p className="text-ink-3 mt-3 text-[0.8125rem]">
          {hidden} more between them, all on their own pages.
        </p>
      )}
    </section>
  )
}
