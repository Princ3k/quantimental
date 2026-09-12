'use client'

import { useState } from 'react'

import { cn } from '@/lib/utils'
import type { Composite, SectorSummary } from '@/lib/types'

/**
 * What the risk appetite number means, shown as how today's was built.
 *
 * A 0-100 score with no explanation asks to be trusted, which is the opposite
 * of this product's stance everywhere else. And the number cannot be
 * reconciled with the list beside it: "What moved this week" shows only the
 * moves large enough to be notable, while *every* non-neutral instrument moves
 * the score — so gold easing back contributes 2.9 points while never appearing
 * in the list.
 *
 * Rather than explain the formula in prose, this shows the actual arithmetic
 * for today. Every line is a real contribution, they sum with 50 to the score
 * on screen, and a reader can check that themselves.
 */
export function RiskExplainer({
  composite,
  sectors,
}: {
  composite: Composite
  sectors: SectorSummary
}) {
  const [open, setOpen] = useState(false)

  // Largest effect first: the reason for today's reading, in order.
  const contributions = [...composite.contributions].sort(
    (a, b) => Math.abs(b.effect) - Math.abs(a.effect),
  )

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors"
      >
        {open ? 'Hide' : 'What is this?'}
        <span aria-hidden className="ml-1">{open ? '↑' : '↓'}</span>
      </button>

      {open && (
        <div className="text-ink-2 mt-3 space-y-3 text-[0.8125rem] leading-relaxed">
          <p>
            Whether money moved toward risk or away from it over the past week.{' '}
            <span className="text-ink">50 is neutral</span> — above it, investors leaned in;
            below, they pulled back.
          </p>

          {contributions.length > 0 && (
            <div>
              <p className="eyebrow mb-2">How today&rsquo;s {composite.score} was reached</p>
              <ul className="space-y-1">
                <li className="text-ink-3 flex items-baseline justify-between gap-3">
                  <span>Neutral starting point</span>
                  <span className="tnum font-mono">50.0</span>
                </li>
                {contributions.map((item) => (
                  <li key={item.name} className="flex items-baseline justify-between gap-3">
                    <span>{item.name}</span>
                    <span
                      className={cn(
                        'tnum shrink-0 font-mono',
                        item.effect >= 0 ? 'text-up' : 'text-down',
                      )}
                    >
                      {item.effect >= 0 ? '+' : ''}
                      {item.effect.toFixed(1)}
                    </span>
                  </li>
                ))}
                <li className="rule-t text-ink flex items-baseline justify-between gap-3 pt-1.5 font-medium">
                  <span>{composite.label}</span>
                  <span className="tnum font-mono">{composite.score}</span>
                </li>
              </ul>
            </div>
          )}

          <p>
            Each move is measured against how much{' '}
            <span className="text-ink">that instrument normally moves</span>, not in raw
            percent — so an unusually large shift in bond yields counts for more than a
            routine one. Related instruments are averaged rather than added, because
            high-yield and investment-grade credit sell off together and one story should
            not vote twice.
          </p>

          {sectors.available && sectors.breadth !== null && (
            <p>
              Breadth is folded in too: {sectors.breadth}% of sectors rose this week, and a
              market carried by two names behaves differently from one where most things go
              up, even at the same index level.
            </p>
          )}

          <p className="text-ink-3">
            Small moves still count, so an instrument can nudge the score without being
            notable enough to list above. This is not a forecast and not a market-direction
            call — stocks can rise on a risk-off reading. It describes the character of the
            week&rsquo;s moves, not where they go next.
          </p>
        </div>
      )}
    </div>
  )
}
