'use client'

import { ChevronDown, GraduationCap } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Verdict } from '@/components/verdict'
import { cn } from '@/lib/utils'
import { ACTION_MEANING } from '@/lib/presentation'
import { useStoredValue } from '@/lib/use-local-storage'
import type { RecommendationAction } from '@/lib/types'

const STORAGE_KEY = 'quantimental.howToRead.open'

const LEGEND: Array<{ action: RecommendationAction; label: string }> = [
  { action: 'strong_buy', label: 'Strong Buy' },
  { action: 'buy', label: 'Buy' },
  { action: 'hold', label: 'Hold' },
  { action: 'sell', label: 'Sell' },
  { action: 'strong_sell', label: 'Strong Sell' },
]

/** Open on a first visit; collapsed once the reader closes it. */
function parseOpen(raw: string | null): boolean {
  return raw === null ? true : raw === 'true'
}

/**
 * A first-run explainer of what the five verdicts mean.
 *
 * Open by default for a new visitor, because the whole product rests on
 * understanding this scale, and collapsed once dismissed so it does not nag a
 * returning user.
 */
export function HowToRead() {
  const [open, setOpen] = useStoredValue(STORAGE_KEY, true, parseOpen)

  return (
    <Card className="gap-0 overflow-hidden py-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="hover:bg-muted/50 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors"
      >
        <GraduationCap className="text-primary size-4 shrink-0" aria-hidden />
        <span className="flex-1 text-sm font-medium">New here? How to read these cards</span>
        <ChevronDown
          className={cn('text-muted-foreground size-4 transition-transform', open && 'rotate-180')}
          aria-hidden
        />
      </button>

      {open && (
        <div className="border-border space-y-4 border-t px-4 py-4">
          <p className="text-muted-foreground text-sm leading-relaxed">
            Each card gives one stock a verdict on a five-point scale. The verdict combines two
            things: what the <strong className="text-foreground">price chart</strong> has been
            doing, and the <strong className="text-foreground">mood</strong> in news and social
            posts about it. Underneath, you can always open the reasoning.
          </p>

          <dl className="space-y-2.5">
            {LEGEND.map(({ action, label }) => (
              <div key={action} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
                <dt className="sm:w-32 sm:shrink-0">
                  <Verdict action={action} label={label} />
                </dt>
                <dd className="text-muted-foreground text-sm leading-relaxed">
                  {ACTION_MEANING[action]}
                </dd>
              </div>
            ))}
          </dl>

          <p className="text-muted-foreground border-border border-t pt-3 text-xs leading-relaxed">
            A verdict describes what the signals currently show — it is not a recommendation to
            trade, and none of it accounts for your own goals, timeline, or risk tolerance.
          </p>
        </div>
      )}
    </Card>
  )
}
