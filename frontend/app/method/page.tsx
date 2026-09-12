import type { Metadata } from 'next'
import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'
import { VERDICT_LABEL, getBacktest, type BacktestBucket } from '@/lib/backtest'
import { SITE_URL } from '@/lib/snapshot'
import { cn } from '@/lib/utils'

/**
 * Why this app does not tell you what to buy.
 *
 * The page exists because the claim "we don't predict" is worth nothing
 * unasserted. We built a five-point buy/sell scale, measured it, found it was
 * backwards, and deleted it — and until this page, a visitor had no way of
 * knowing any of that had happened.
 *
 * Every figure is read from the published backtest rather than written into
 * the copy. The two drifted apart once already, which is exactly the failure
 * this page exists to make impossible.
 */

export const revalidate = 86_400

export const metadata: Metadata = {
  title: 'Why we stopped predicting',
  description:
    'We built a buy/sell scale, tested it over 3,792 readings, and found it was backwards. Here is the data, and what we did about it.',
  alternates: { canonical: '/method' },
  openGraph: {
    title: 'Why we stopped predicting',
    description:
      'We built a buy/sell scale, tested it, and found it was backwards. Here is the data.',
    url: `${SITE_URL}/method`,
  },
}

export default async function MethodPage() {
  const backtest = await getBacktest()

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-2xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> Back
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight text-balance sm:text-3xl">
          Why we stopped predicting
        </h1>

        <div className="mt-7 space-y-5 text-[0.9375rem] leading-relaxed">
          <p>
            This app used to score every stock on a five-point scale, from strong buy to
            strong sell. It doesn&rsquo;t any more. This page is the reason, with the numbers
            that produced it.
          </p>
          <p>
            We replayed the engine across{' '}
            {backtest ? `${backtest.observations.toLocaleString()} readings` : 'thousands of readings'}{' '}
            of history, computing each verdict only from data available on the day it was
            made, then measuring what actually happened next. The question was simple: when
            it said buy, did the stock beat simply holding?
          </p>
        </div>

        {backtest ? (
          <>
            <p className="mt-8 text-[0.9375rem] leading-relaxed">
              It did the opposite. The more bullish the call, the worse the stock did.
            </p>

            <Results backtest={backtest} />

            <div className="mt-10 space-y-5 text-[0.9375rem] leading-relaxed">
              <p>
                Read down the column. The average return rises steadily from the most bullish
                verdict to the most bearish — a clean inversion of what the scale claimed.
                Holding these names over the same windows returned{' '}
                <span className="tnum">{backtest.baseline_return.toFixed(2)}%</span>, and the
                strongest buys returned less than that.
              </p>
              {backtest.directional_accuracy !== null && (
                <p>
                  Its directional calls were right{' '}
                  <span className="tnum">{backtest.directional_accuracy.toFixed(1)}%</span> of the
                  time. A coin flip is 50%.
                </p>
              )}
              <p>
                <span className="text-ink font-medium">
                  We did not invert the signal and ship that instead.
                </span>{' '}
                A result that survives one universe over one period is a hypothesis, not an
                edge, and building a product on a backwards signal because it backtested well
                is the same mistake in the other direction. The honest response to
                &ldquo;our forecast was wrong&rdquo; is to stop forecasting.
              </p>
            </div>

            <section className="rule-t mt-10 pt-8">
              <h2 className="text-lg font-medium tracking-tight">What this does not measure</h2>
              <p className="text-ink-3 mt-2 text-[0.875rem] leading-relaxed">
                A backtest quoted without its limits is how a null result turns into a
                marketing claim. These are ours.
              </p>
              <ul className="mt-5 space-y-3">
                {backtest.limitations.map((limitation) => (
                  <li
                    key={limitation}
                    className="text-ink-2 border-rule-strong border-l-2 pl-3.5 text-[0.875rem] leading-relaxed"
                  >
                    {limitation}
                  </li>
                ))}
              </ul>
            </section>

            <section className="rule-t mt-10 pt-8">
              <h2 className="text-lg font-medium tracking-tight">What we do instead</h2>
              <div className="mt-4 space-y-4 text-[0.9375rem] leading-relaxed">
                <p>
                  Describe what has already happened, in language you can check against the
                  chart and the headlines on the same page. How a stock moved today and over
                  the past fortnight. Whether that move was large{' '}
                  <span className="text-ink">for that stock</span>, measured against its own
                  daily range rather than a fixed percentage. Whether the market and its
                  sector moved with it. What was published about it.
                </p>
                <p>
                  None of that is a forecast, and none of it needs to be. Knowing what
                  happened and why is useful on its own — and unlike a forecast, you can
                  check whether we got it right.
                </p>
              </div>
            </section>

            <p className="text-ink-3 rule-t mt-10 pt-6 text-[0.8125rem] leading-relaxed">
              Measured over {backtest.universe.length} tickers,{' '}
              {backtest.period.start} to {backtest.period.end}, with each verdict judged{' '}
              {backtest.horizon_days} trading days out and signals spaced{' '}
              {backtest.rebalance_days} days apart to avoid overlapping windows.{' '}
              <a
                href="https://github.com/Princ3k/quantimental/blob/main/public/backtest.json"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-ink underline underline-offset-2 transition-colors"
              >
                The raw results
              </a>{' '}
              and{' '}
              <a
                href="https://github.com/Princ3k/quantimental/blob/main/backend/app/services/backtest/engine.py"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-ink underline underline-offset-2 transition-colors"
              >
                the code that produced them
              </a>{' '}
              are both public. This is not financial advice.
            </p>
          </>
        ) : (
          <p className="text-ink-3 mt-8 text-[0.9375rem] leading-relaxed">
            The measurements could not be loaded right now. They are published at{' '}
            <a
              href="https://github.com/Princ3k/quantimental/blob/main/public/backtest.json"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-ink underline underline-offset-2"
            >
              backtest.json
            </a>
            .
          </p>
        )}
      </main>
    </div>
  )
}

/**
 * The table.
 *
 * Ordered most bullish to most bearish so the inversion is visible by reading
 * down the mean column — the ordering is the finding, so the layout carries it
 * rather than relying on the prose to point it out.
 */
function Results({ backtest }: { backtest: Awaited<ReturnType<typeof getBacktest>> }) {
  if (!backtest) return null

  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full min-w-[30rem] text-[0.875rem]">
        <thead>
          <tr className="text-ink-3 border-rule border-b text-left">
            <th scope="col" className="eyebrow pb-2 font-normal">Verdict</th>
            <th scope="col" className="eyebrow pb-2 text-right font-normal">Readings</th>
            <th scope="col" className="eyebrow pb-2 text-right font-normal">Avg return</th>
            <th scope="col" className="eyebrow pb-2 text-right font-normal">vs holding</th>
          </tr>
        </thead>
        <tbody>
          {backtest.buckets.map((bucket) => (
            <Row key={bucket.action} bucket={bucket} />
          ))}
        </tbody>
      </table>
      <p className="text-ink-3 mt-3 text-[0.8125rem] leading-relaxed">
        Returns are averages over {backtest.horizon_days} trading days. Rows marked
        &ldquo;significant&rdquo; clear two standard errors — with samples this size that is a
        sanity filter, not a formal test.
      </p>
    </div>
  )
}

function Row({ bucket }: { bucket: BacktestBucket }) {
  const beat = bucket.edge_vs_baseline > 0

  return (
    <tr className="border-rule border-b last:border-0">
      <td className="py-2.5">
        {VERDICT_LABEL[bucket.action]}
        {bucket.significant && (
          <span className="text-ink-3 ml-2 text-[0.6875rem]">significant</span>
        )}
      </td>
      <td className="tnum py-2.5 text-right font-mono">{bucket.count.toLocaleString()}</td>
      <td className="tnum py-2.5 text-right font-mono">{bucket.mean_return.toFixed(2)}%</td>
      <td
        className={cn(
          'tnum py-2.5 text-right font-mono',
          // Colour marks direction against the baseline, which on this page is
          // the finding rather than a value judgement about the verdict.
          beat ? 'text-up' : 'text-down',
        )}
      >
        {bucket.edge_vs_baseline > 0 ? '+' : ''}
        {bucket.edge_vs_baseline.toFixed(2)}%
      </td>
    </tr>
  )
}
