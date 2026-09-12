'use client'

import Link from 'next/link'

import { useStoredValue } from '@/lib/use-local-storage'

const STORAGE_KEY = 'quantimental.howToRead.open'

function parseOpen(raw: string | null): boolean {
  return raw === null ? true : raw === 'true'
}

/**
 * A short note on what the descriptions mean, and what this tool will not do.
 *
 * It says plainly that the buy/sell scale was removed and why the backtest
 * forced that. A tool that quietly drops a feature teaches nothing; one that
 * says "we tried to predict, we measured it, it did not work" tells the reader
 * exactly how much to trust what remains.
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
            Each stock gets one sentence describing what it has actually done — today, and over
            the past two weeks — followed by anything unusual about it and the headlines we
            read. Every line is checkable against the chart and the links beside it.
          </p>
          <p>
            &ldquo;Unusual&rdquo; is measured against each stock&rsquo;s own behaviour, not a
            fixed percentage. A 3% day is a big move for{' '}
            <span className="text-ink">KO</span> and an ordinary one for{' '}
            <span className="text-ink">TSLA</span>, so we compare today&rsquo;s move to that
            stock&rsquo;s typical daily range rather than to every other stock.
          </p>
          <p className="text-ink-3">
            We do not tell you what to buy. We tried: an earlier version scored every stock on
            a five-point buy-to-sell scale, and testing it over 3,792 readings found it was
            backwards — the stocks it called strong buys underperformed, and its directional
            calls were right 48.5% of the time, worse than a coin flip. So the scale is gone.{' '}
            <Link href="/method" className="text-ink underline underline-offset-2">
              The numbers are here
            </Link>
            . What is left describes the present, which we can stand behind. None of this is
            financial advice.
          </p>
        </div>
      )}
    </div>
  )
}
