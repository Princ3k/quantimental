'use client'

import { useState } from 'react'
import { ChevronDown, Info, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { InfoTip } from '@/components/info-tip'
import { ScoreBar } from '@/components/score-bar'
import { Sparkline } from '@/components/sparkline'
import { ConfidenceMeter, Verdict } from '@/components/verdict'
import { cn } from '@/lib/utils'
import {
  TREND_LABEL,
  VOLATILITY_LABEL,
  VOLATILITY_MEANING,
  formatPercent,
  formatPrice,
  formatVolume,
} from '@/lib/presentation'
import type { StockSignal } from '@/lib/types'

interface StockCardProps {
  signal: StockSignal
  onRemove?: (ticker: string) => void
}

/**
 * One stock, readable at a glance.
 *
 * Information order is deliberate and follows what a first-time investor
 * actually needs, in order:
 *
 *   1. Which company, and what is it doing today (price + change)
 *   2. The verdict, in one word
 *   3. Why, in one sentence
 *   4. How much to trust it
 *   5. Everything else, collapsed behind "Show the details"
 *
 * The old card led with a dense two-column grid of RSI / MA50 / MA200 /
 * hybrid-weight readouts, which is the right information in the wrong order
 * for this audience.
 */
export function StockCard({ signal, onRemove }: StockCardProps) {
  const [showDetails, setShowDetails] = useState(false)

  const { recommendation, technical_analysis: ta, sentiment_analysis: sentiment } = signal
  const isUp = signal.change >= 0

  return (
    <Card className="gap-0 overflow-hidden py-0">
      <div className="space-y-4 p-5">
        {/* 1. Identity and today's move */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-lg font-semibold">{signal.ticker}</h3>
              {signal.sector && (
                <Badge variant="muted" className="hidden sm:inline-flex">
                  {signal.sector}
                </Badge>
              )}
            </div>
            <p className="text-muted-foreground truncate text-sm">{signal.company_name}</p>
          </div>

          {onRemove && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onRemove(signal.ticker)}
              aria-label={`Remove ${signal.ticker} from your list`}
              className="text-muted-foreground hover:text-negative -mt-1 -mr-1"
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>

        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="tabular text-2xl font-semibold">{formatPrice(signal.price)}</p>
            <p
              className={cn(
                'tabular text-sm font-medium',
                isUp ? 'text-positive' : 'text-negative',
              )}
            >
              {isUp ? '▲' : '▼'} {formatPrice(Math.abs(signal.change))} (
              {formatPercent(signal.change_percent)}) today
            </p>
          </div>
          <div className="w-28 shrink-0">
            <Sparkline data={signal.price_history} height={36} />
          </div>
        </div>

        {/* 2 & 3. The verdict and the single most important reason */}
        <div className="bg-muted/50 space-y-3 rounded-lg p-4">
          <Verdict action={recommendation.action} label={recommendation.label} size="lg" />
          <p className="text-sm leading-relaxed">{recommendation.summary}</p>

          {recommendation.pattern && (
            <div className="border-primary/30 bg-accent/40 rounded-md border-l-2 px-3 py-2">
              <p className="text-accent-foreground text-xs font-semibold">
                {recommendation.pattern.name}
              </p>
              <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                {recommendation.pattern.description}
              </p>
            </div>
          )}
        </div>

        {/* 4. How much to trust it */}
        <ConfidenceMeter value={recommendation.confidence} />

        {/* 5. Everything else */}
        <Button
          variant="ghost"
          onClick={() => setShowDetails((open) => !open)}
          aria-expanded={showDetails}
          className="text-muted-foreground hover:text-foreground w-full justify-center text-xs"
        >
          {showDetails ? 'Hide the details' : 'Show the details'}
          <ChevronDown
            className={cn('size-3.5 transition-transform', showDetails && 'rotate-180')}
            aria-hidden
          />
        </Button>
      </div>

      {showDetails && (
        <div className="border-border bg-muted/20 space-y-5 border-t p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <ScoreBar
              label="Chart score"
              score={signal.technical_rating}
              glossaryKey="technicalScore"
            />
            <ScoreBar
              label="Mood score"
              score={signal.sentiment_rating}
              glossaryKey="sentimentScore"
              unavailableReason={sentiment.reason}
            />
          </div>

          <section>
            <h4 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
              What the chart shows
            </h4>
            <dl className="grid gap-x-4 gap-y-2.5 text-sm sm:grid-cols-2">
              <Fact label="Direction" value={TREND_LABEL[ta.trend]} />
              <Fact
                label="Momentum"
                value={ta.momentum.label}
                hint={ta.momentum.meaning}
                glossaryKey="momentum"
              />
              <Fact
                label="Price swings"
                value={VOLATILITY_LABEL[ta.volatility]}
                hint={VOLATILITY_MEANING[ta.volatility]}
                glossaryKey="volatility"
              />
              <Fact label="Average daily volume" value={formatVolume(ta.avg_volume)} />
            </dl>

            {(ta.golden_cross || ta.death_cross) && (
              <div className="mt-3">
                <Badge variant={ta.golden_cross ? 'positive' : 'negative'}>
                  {ta.golden_cross ? 'Golden cross' : 'Death cross'}
                </Badge>
                <span className="ml-2 inline-flex align-middle">
                  <InfoTip entry={ta.golden_cross ? 'goldenCross' : 'deathCross'} />
                </span>
              </div>
            )}
          </section>

          <section>
            <h4 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
              Why we reached this view
            </h4>
            <ul className="space-y-2">
              {recommendation.reasons.map((reason) => (
                <li key={reason} className="text-muted-foreground flex gap-2 text-sm leading-relaxed">
                  <span aria-hidden className="text-primary mt-0.5 shrink-0">
                    •
                  </span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </section>

          {!signal.metadata.data_quality.sufficient && (
            <p className="text-caution-foreground bg-caution-subtle flex gap-2 rounded-md p-3 text-xs">
              <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>
                This stock has only {signal.metadata.data_quality.bars} days of price history, which
                is not enough for a reliable reading. Treat the scores above with caution.
              </span>
            </p>
          )}
        </div>
      )}
    </Card>
  )
}

function Fact({
  label,
  value,
  hint,
  glossaryKey,
}: {
  label: string
  value: string
  hint?: string
  glossaryKey?: Parameters<typeof InfoTip>[0]['entry']
}) {
  return (
    <div>
      <dt className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
        {label}
        {glossaryKey && <InfoTip entry={glossaryKey} />}
      </dt>
      <dd className="font-medium">{value}</dd>
      {hint && <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">{hint}</p>}
    </div>
  )
}
