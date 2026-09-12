'use client'

import { useState } from 'react'

import { DeepDive } from '@/components/deep-dive'
import { Sparkline } from '@/components/sparkline'
import { Confidence, Verdict } from '@/components/verdict'
import { cn } from '@/lib/utils'
import {
  TREND_LABEL,
  VOLATILITY_LABEL,
  formatPercent,
  formatPrice,
  formatVolume,
} from '@/lib/presentation'
import type { Headline, StockSignal } from '@/lib/types'

/*
 * One stock.
 *
 * Reading order is the product decision, not a layout preference: identity,
 * price, then **the explanation**, then the verdict. The explanation describes
 * what has already happened and is checkable. The verdict predicts, and a
 * backtest found no significant edge in it — so it sits below the sentence it
 * used to dominate.
 *
 * There is one surface, no nested panels. Sections are separated by space and
 * hairlines.
 */
export function StockCard({
  signal,
  onRemove,
  onDeepDive,
}: {
  signal: StockSignal
  onRemove?: (ticker: string) => void
  /** Replaces this card's data with a full-depth analysis including sentiment. */
  onDeepDive?: (signal: StockSignal) => void
}) {
  const [open, setOpen] = useState(false)
  const { recommendation: rec, technical_analysis: ta, sentiment_analysis: sentiment } = signal
  const up = signal.change >= 0

  return (
    <article className="group border-rule bg-surface rounded-lg border p-5 sm:p-6">
      {/* Identity */}
      <div className="flex items-baseline justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-mono text-[0.9375rem] font-medium tracking-tight">{signal.ticker}</h3>
          <p className="text-ink-3 mt-0.5 truncate text-[0.8125rem]">{signal.company_name}</p>
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={() => onRemove(signal.ticker)}
            aria-label={`Remove ${signal.ticker}`}
            className="text-ink-3 hover:text-ink -mt-1 -mr-1 shrink-0 rounded p-1.5 text-xs opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
          >
            Remove
          </button>
        )}
      </div>

      {/* Price — the figure people came for */}
      <div className="mt-5 flex items-end justify-between gap-5">
        <div>
          <p className="tnum font-mono text-[2.125rem] leading-none font-medium tracking-tight">
            {formatPrice(signal.price)}
          </p>
          <p className={cn('tnum mt-2 text-sm', up ? 'text-up' : 'text-down')}>
            {up ? '↑' : '↓'} {formatPercent(signal.change_percent)}
            <span className="text-ink-3"> today</span>
          </p>
        </div>
        <div className="w-24 shrink-0 sm:w-28">
          <Sparkline data={signal.price_history} height={38} />
        </div>
      </div>

      {/* The explanation — the product */}
      <p className="mt-5 text-[0.9375rem] leading-relaxed text-balance">{rec.summary}</p>

      {rec.pattern && (
        <p className="text-ink-2 border-rule-strong mt-3 border-l-2 pl-3 text-[0.8125rem] leading-relaxed">
          <span className="text-ink font-medium">{rec.pattern.name}.</span>{' '}
          {rec.pattern.description}
        </p>
      )}

      {/* The verdict — present, secondary */}
      <div className="rule-t mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 pt-4">
        <Verdict action={rec.action} />
        <Confidence value={rec.confidence} />
      </div>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-ink-3 hover:text-ink mt-3 text-[0.8125rem] transition-colors"
      >
        {open ? 'Hide the numbers' : 'Show the numbers'}
        <span aria-hidden className="ml-1 inline-block">{open ? '↑' : '↓'}</span>
      </button>

      {open && (
        <div className="rule-t mt-4 space-y-5 pt-5">
          {/* Two columns, always. `sm:` is viewport-based, but these cards sit
              in a two-up grid and are ~290px wide on desktop — four columns
              there wraps every label onto two lines. */}
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
            {/* Values are phrased, not abbreviated. An earlier pass rendered
                this as "35 pctl", which is precisely the bare jargon this
                product exists to avoid. */}
            <Figure
              label="Chart strength"
              value={`${signal.technical_rating}/100`}
              note={`Stronger than ${signal.technical_rating}% of readings we've measured`}
            />
            <Figure
              label="Market mood"
              value={
                sentiment.available && sentiment.rating !== null
                  ? `${sentiment.rating}/100`
                  : 'Not measured'
              }
              note={
                sentiment.available
                  ? 'How positive news and social posts have been'
                  : 'Gathered only for detailed single-stock analysis'
              }
            />
            <Figure
              label="Direction"
              value={TREND_LABEL[ta.trend]}
              note="Where the 20-day average has been heading"
            />
            <Figure
              label="Price swings"
              value={VOLATILITY_LABEL[ta.volatility]}
              note="How much it moves on a typical day"
            />
            <Figure label="Momentum" value={ta.momentum.label} note={ta.momentum.meaning} />
            <Figure
              label="Average volume"
              value={formatVolume(ta.avg_volume)}
              note="Shares traded on a typical day"
            />
            <Figure
              label="50-day average"
              value={formatPrice(ta.sma_50)}
              note="Average closing price over the last 50 trading days"
            />
            <Figure
              label="200-day average"
              value={ta.sma_200 ? formatPrice(ta.sma_200) : 'Not enough history'}
              note="The long-term trend line traders watch most"
            />
          </dl>

          {(ta.golden_cross || ta.death_cross) && (
            <p className={cn('text-[0.8125rem]', ta.golden_cross ? 'text-up' : 'text-down')}>
              {ta.golden_cross
                ? 'The 50-day average just crossed above the 200-day — a widely watched bullish marker.'
                : 'The 50-day average just crossed below the 200-day — a widely watched bearish marker.'}
            </p>
          )}

          <div>
            <p className="eyebrow mb-2.5">Why</p>
            <ul className="space-y-2">
              {rec.reasons.map((reason) => (
                <li key={reason} className="text-ink-2 text-[0.8125rem] leading-relaxed">
                  {reason}
                </li>
              ))}
            </ul>
          </div>

          {!sentiment.available && (
            <div className="space-y-1.5">
              {sentiment.reason && (
                <p className="text-ink-3 text-[0.8125rem] leading-relaxed">{sentiment.reason}</p>
              )}
              {onDeepDive && <DeepDive ticker={signal.ticker} onResult={onDeepDive} />}
            </div>
          )}

          {sentiment.available && (
            <>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
                <Figure
                  label="Mentions"
                  value={sentiment.mentions.toLocaleString()}
                  note="Recent news articles and social posts we read"
                />
                <Figure
                  label="Attention"
                  value={
                    sentiment.mention_velocity === 'rising'
                      ? 'Picking up'
                      : sentiment.mention_velocity === 'falling'
                        ? 'Fading'
                        : 'Steady'
                  }
                  note="Whether people are talking about it more or less than before"
                />
              </dl>

              <Headlines items={sentiment.headlines} />
            </>
          )}

          {!signal.metadata.data_quality.sufficient && (
            <p className="text-down text-[0.8125rem] leading-relaxed">
              Only {signal.metadata.data_quality.bars} days of price history — not enough for a
              reliable reading.
            </p>
          )}
        </div>
      )}
    </article>
  )
}

/**
 * The stories the sentiment score was computed from.
 *
 * A score on its own asks to be believed; the headlines behind it can be
 * checked. This is the part of the card a newer investor can actually act on,
 * so the titles are the content and the score is the summary of them.
 */
function Headlines({ items }: { items?: Headline[] }) {
  if (!items?.length) return null

  return (
    <div>
      <p className="eyebrow mb-2.5">What we read</p>
      <ul className="space-y-2.5">
        {items.map((item) => (
          <li key={item.url || item.title}>
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-ink-2 hover:text-ink text-[0.8125rem] leading-relaxed transition-colors"
              >
                {item.title}
              </a>
            ) : (
              <span className="text-ink-2 text-[0.8125rem] leading-relaxed">{item.title}</span>
            )}
            {item.source && <span className="text-ink-3 ml-1.5 text-[0.75rem]">{item.source}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * A labelled figure with its meaning stated underneath.
 *
 * The note is always visible rather than hidden behind a tooltip. A reader who
 * does not know what a 50-day average is will not hover over it to find out —
 * they will skip it, which defeats the point.
 */
function Figure({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className="tnum mt-1 text-[0.9375rem] font-medium">{value}</dd>
      {note && <p className="text-ink-3 mt-1 text-xs leading-snug">{note}</p>}
    </div>
  )
}
