'use client'

import Link from 'next/link'

import { cn } from '@/lib/utils'
import type { SectorSummaryRow } from '@/lib/sectors'

/**
 * Every sector, ranked, on the dashboard.
 *
 * The desk above already says "30% of sectors rising, Energy leading" and then
 * leaves the obvious question — *which* sectors? — unanswered. This is the
 * answer, and it is also the route into the sector pages.
 *
 * Bars are scaled to the largest move on the day rather than a fixed
 * percentage, so the shape shows relative strength on *this* day instead of
 * flattening to nothing on a quiet one. They are deliberately not a chart: no
 * axis, no ticks, just enough length to rank at a glance before the number
 * beside them gives the exact figure.
 */
export function SectorStrip({ sectors }: { sectors: SectorSummaryRow[] }) {
  if (sectors.length === 0) return null

  const widest = Math.max(...sectors.map((s) => Math.abs(s.change_percent)), 0.1)

  return (
    <section className="rule-t py-10 sm:py-12">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium tracking-tight sm:text-2xl">Sectors</h2>
          <p className="text-ink-3 mt-1.5 text-[0.8125rem] leading-relaxed">
            Median move of each sector&rsquo;s companies this session, and how many
            of them rose.
          </p>
        </div>
      </div>

      {/* Two columns only once there is room for a full sector name beside
          its bar and figures. At the `sm` breakpoint each column was ~280px
          and "Consumer Discretionary" truncated to "Consumer Discreti...". */}
      <ul className="grid gap-x-10 gap-y-1 lg:grid-cols-2">
        {sectors.map((sector) => (
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
    </section>
  )
}
