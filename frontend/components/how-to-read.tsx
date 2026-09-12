'use client'

import { useStoredValue } from '@/lib/use-local-storage'

const STORAGE_KEY = 'quantimental.howToRead.open'

function parseOpen(raw: string | null): boolean {
  return raw === null ? true : raw === 'true'
}

/**
 * A short note on what the verdicts mean and what they are worth.
 *
 * It states the backtest result plainly. An investing tool that shows a "Buy"
 * without saying whether its buys have ever worked is asking for trust it has
 * not earned.
 */
export function HowToRead() {
  const [open, setOpen] = useStoredValue(STORAGE_KEY, true, parseOpen)

  return (
    <div className="rule-t pt-5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors"
      >
        How to read this
        <span aria-hidden className="ml-1">{open ? '↑' : '↓'}</span>
      </button>

      {open && (
        <div className="text-ink-2 mt-4 max-w-2xl space-y-3 text-[0.8125rem] leading-relaxed">
          <p>
            Each stock gets a one-line description of what its chart and the news around it are
            doing. That part describes the present, and you can check it.
          </p>
          <p>
            Each also gets a verdict on a five-point scale, scored against how unusual the
            reading is: the strongest 5% of readings we have measured are{' '}
            <span className="text-ink">strong buy</span>, the weakest 5%{' '}
            <span className="text-ink">strong sell</span>, and the middle half{' '}
            <span className="text-ink">hold</span>. It is relative — in a falling market the
            best available reading still scores highly.
          </p>
          <p className="text-ink-3">
            We backtested those verdicts over 1,888 readings across five years. None beat simply
            holding by more than statistical noise, and the more bullish calls did slightly
            worse. Treat the verdict as a label on a measurement, not a recommendation — and
            none of this is financial advice.
          </p>
        </div>
      )}
    </div>
  )
}
