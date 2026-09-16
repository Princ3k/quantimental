import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { PriceChart } from '@/components/price-chart'
import { FilingLink } from '@/components/filing-link'
import { SiteHeader } from '@/components/site-header'
import { StockDetail } from '@/components/stock-detail'
import { normalizeApiBase } from '@/lib/api'
import { slugify } from '@/lib/sectors'
import { isCurrentSession, sessionLabel } from '@/lib/session'
import { SITE_URL, getSnapshot, getSnapshotStock } from '@/lib/snapshot'

/*
 * Through the shared normaliser, not a local `.replace(/\/+$/, '')`.
 *
 * The deployed value is a bare host with no scheme, which Node's fetch cannot
 * parse as absolute — it threw TypeError on every render, the check failed
 * open, and /stock/zzzzzz returned 200 in production while 404ing locally.
 * lib/api.ts had already solved this for the browser; rolling a second,
 * weaker version here undid it server-side.
 */
const API_BASE = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL)

/**
 * One stock, at its own URL.
 *
 * This is the app's front door, not a convenience. Before these pages existed
 * there was a single route: you could not send anyone a link to a stock, search
 * engines had nothing to index, and pasting the URL anywhere produced a bare
 * domain with no card. Every visitor had to arrive at the homepage and search.
 *
 * The page renders from the static snapshot so it is complete before any
 * JavaScript runs — which is what a crawler sees, and what someone on a slow
 * connection sees first. `StockDetail` then enriches it client-side with the
 * live chart and news. Crawlers get the static half and never touch the API.
 */

// Must be a literal — Next statically analyses this export, so an imported
// constant fails the build with "Invalid segment configuration export".
// Kept in step with SNAPSHOT_REVALIDATE_SECONDS in lib/snapshot.ts.
export const revalidate = 1800

/**
 * Pre-render the S&P 500. Anything else — RYCEY, SHOP.TO, an ETF — still
 * resolves, rendered on demand, because `dynamicParams` defaults to true.
 */
export async function generateStaticParams() {
  const snapshot = await getSnapshot()
  if (!snapshot) return []
  return snapshot.stocks.map((stock) => ({ ticker: stock.t.toLowerCase() }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }>
}): Promise<Metadata> {
  const { ticker } = await params
  const stock = await getSnapshotStock(ticker)
  const symbol = ticker.toUpperCase()

  if (!stock) {
    return {
      title: `${symbol} — what's happening`,
      description: `What ${symbol} is doing today and over the past two weeks, in plain English.`,
    }
  }

  // The description is the sentence the page actually leads with. It reads as
  // a real search snippet because it is one, rather than a keyword string
  // assembled for crawlers.
  const title = `${stock.n} (${stock.t}) — what's happening`
  const path = `/stock/${stock.t.toLowerCase()}`

  return {
    title,
    description: stock.h,
    alternates: { canonical: path },
    openGraph: {
      title,
      description: stock.h,
      url: `${SITE_URL}${path}`,
      siteName: 'Quantimental',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description: stock.h,
    },
  }
}

/**
 * Does this symbol exist at all?
 *
 * Only consulted for tickers outside the scanned universe, which is a small
 * fraction of requests — the 503 pre-rendered pages never reach it. Failures
 * resolve to `true` on purpose: an upstream outage should not start returning
 * 404s for real companies, which is the more damaging error of the two.
 */
async function tickerExists(symbol: string): Promise<{ exists: boolean; why: string }> {
  if (!API_BASE || API_BASE.includes('localhost')) {
    // No API configured for this environment. Failing open is right, but
    // silently doing so is how /stock/zzzzzz kept returning 200 while the same
    // code 404'd locally — so the reason travels with the answer.
    return { exists: true, why: 'no-api-configured' }
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/v1/signals/search?q=${encodeURIComponent(symbol)}`,
      { next: { revalidate: 86_400 } },
    )
    if (!response.ok) return { exists: true, why: `search-http-${response.status}` }

    const payload = (await response.json()) as { results?: { ticker: string }[] }
    const matched = (payload.results ?? []).some((r) => r.ticker.toUpperCase() === symbol)
    return { exists: matched, why: matched ? 'found' : 'not-found' }
  } catch (error) {
    return { exists: true, why: `search-failed-${(error as Error).name}` }
  }
}

/**
 * Coverage as a phrase rather than a rate.
 *
 * "29.5 articles/day" is a number nobody asked for; "30 times a day" is how a
 * person would say it. Below one a day the rate stops being the useful unit
 * and the gap between stories is.
 */
function formatCoverage(perDay: number): string {
  // Returns the whole phrase, including its own hedge, because the hedge
  // differs by magnitude. The sentence that consumes it must not end in
  // "about" either: "written about about once every 4 days" was the first two
  // attempts at this.
  if (perDay >= 1.5) return `roughly ${Math.round(perDay)} times a day`
  if (perDay >= 0.8) return 'about once a day'
  if (perDay >= 0.2) return `about once every ${Math.round(1 / perDay)} days`
  return 'rarely — less than once a week'
}

/**
 * When the filing landed, relative to the session it is shown against.
 *
 * Filings accepted after the 4pm close are counted against the next session,
 * so the timestamp routinely belongs to the previous calendar day. Saying
 * "after the previous close" is the difference between a reader trusting the
 * date and thinking we mismatched it.
 */
function filingTiming(acceptedAt: string): string {
  const accepted = new Date(acceptedAt)
  if (Number.isNaN(accepted.getTime())) return ''

  // EDGAR stamps UTC; the close is 4pm in New York.
  const easternHour = (accepted.getUTCHours() + 24 - 4) % 24
  if (easternHour >= 16) return ' after the previous close'
  if (easternHour < 9) return ' before the open'
  return ' during the session'
}


export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>
}) {
  const { ticker } = await params
  const symbol = ticker.toUpperCase()

  // A malformed ticker is a 404, not an API call. Yahoo's symbols allow
  // letters, digits, dots, hyphens and carets (^GSPC).
  if (!/^[A-Z0-9.\-^]{1,12}$/.test(symbol)) notFound()

  const stock = await getSnapshotStock(symbol)
  const session = (await getSnapshot())?.as_of ?? null

  // A symbol that is neither in the scan nor recognised by the market data
  // provider is a 404, not a thin page. Returning 200 for /stock/zzzzzz is a
  // soft 404: search engines index the shell, and a mistyped link looks like a
  // working page with nothing on it.
  const existence = stock ? { exists: true, why: 'in-snapshot' } : await tickerExists(symbol)
  if (!existence.exists) notFound()

  const up = (stock?.c ?? 0) >= 0

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
        {/* Why this page rendered at all, for diagnosing the case where an
            unknown ticker should have 404'd and did not. */}
        <span hidden data-existence={existence.why} />
        <Link
          href="/"
          className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors"
        >
          <span aria-hidden>←</span> All stocks
        </Link>

        <header className="mt-6">
          <h1 className="font-mono text-xl font-medium tracking-tight">{symbol}</h1>
          {stock && (
            <p className="text-ink-3 mt-1 text-[0.9375rem]">
              {stock.n}
              {stock.s && (
                <>
                  {' · '}
                  <Link
                    href={`/sector/${slugify(stock.s)}`}
                    className="hover:text-ink underline underline-offset-2 transition-colors"
                  >
                    {stock.s}
                  </Link>
                </>
              )}
            </p>
          )}
        </header>

        {stock ? (
          <>
            <div className="mt-7 flex items-end gap-5">
              <p className="tnum font-mono text-[2.5rem] leading-none font-medium tracking-tight">
                ${stock.p.toFixed(2)}
              </p>
              <p className={`tnum pb-1 text-sm ${up ? 'text-up' : 'text-down'}`}>
                {up ? '↑' : '↓'} {Math.abs(stock.c).toFixed(2)}%
                <span className="text-ink-3"> today</span>
              </p>
            </div>

            {/* Which day "today" means. The scan publishes after the close and
                is read until the next afternoon, so for part of every day —
                and all weekend — these figures are the previous session's.
                Saying "today" without saying which day is how this page came
                to report Nvidia as little changed while it was down 2.65%. */}
            {session && !isCurrentSession(session) && (
              <p className="text-ink-3 mt-2 text-[0.8125rem]">
                Figures from {sessionLabel(session)}, the last completed session.
              </p>
            )}

            {/* The sentence. Present in the HTML before any script runs, which
                is what a crawler indexes and a shared link previews. */}
            <p className="mt-7 text-lg leading-relaxed text-balance">{stock.h}</p>

            {/* Suppressed for a flat day: "that is 0.0x this stock's typical
                3.5% daily move" is arithmetically true and tells nobody
                anything. The comparison only earns its place once there is a
                move to compare. */}
            {Math.abs(stock.c) >= 0.5 && (
              <p className="text-ink-3 mt-3 text-[0.875rem] leading-relaxed">
                That is {stock.x.toFixed(1)}× this stock&rsquo;s typical{' '}
                {stock.d.toFixed(1)}% daily move
                {stock.x >= 2 ? ' — an unusually large day for it.' : '.'}
              </p>
            )}

            {stock.ctx && (
              <div className="border-rule-strong mt-5 border-l-2 pl-3.5">
                <p className="text-ink-2 text-[0.9375rem] leading-relaxed">{stock.ctx}</p>
                {stock.s && (
                  /* The sentence above names the sector as the reason and then
                     leaves it hanging. This is where that goes. */
                  <Link
                    href={`/sector/${slugify(stock.s)}`}
                    className="text-ink-3 hover:text-ink mt-1.5 inline-block text-[0.8125rem] transition-colors"
                  >
                    What happened across {stock.s} <span aria-hidden>→</span>
                  </Link>
                )}
              </div>
            )}

            {stock.f?.p && (
              <p className="text-ink-3 mt-1.5 text-[0.875rem] leading-relaxed">
                {/* Deliberately a separate sentence from the move. Putting the
                    two in one sentence would imply the filing caused it; they
                    share a day, which is all anyone can say. */}
                It filed an 8-K with the SEC{' '}
                {stock.f.u ? (
                  <FilingLink href={stock.f.u} ticker={stock.t} items={stock.f.i}>
                    {stock.f.p}
                  </FilingLink>
                ) : (
                  <span className="text-ink-2">{stock.f.p}</span>
                )}
                {filingTiming(stock.f.a)}.
              </p>
            )}

            {stock.v !== undefined && (
              <p className="text-ink-3 mt-1.5 text-[0.875rem] leading-relaxed">
                New stories about it appear{' '}
                <span className="text-ink-2">{formatCoverage(stock.v)}</span>
                {stock.vx !== undefined &&
                  ` — ${stock.vx.toFixed(1)}× its own normal coverage`}
                .
              </p>
            )}
          </>
        ) : (
          <p className="text-ink-2 mt-7 text-lg leading-relaxed">
            {symbol} is not in our daily scan of the S&amp;P 500, so there is no
            saved reading for it. We can still analyse it live.
          </p>
        )}

        {/* Its own fetch, so it appears without waiting on the analysis. */}
        <div className="mt-10">
          <PriceChart ticker={symbol} />
        </div>

        {/* Everything below needs the API, so it loads client-side. Crawlers
            index the static half above and never hit our server. */}
        <StockDetail ticker={symbol} />

        <p className="text-ink-3 rule-t mt-12 pt-6 text-[0.8125rem] leading-relaxed">
          Quantimental describes moves that have already happened, using public
          price data and public news. It does not predict, and{' '}
          <Link href="/method" className="hover:text-ink underline underline-offset-2">
            we measured why
          </Link>
          . It does not know your circumstances, and it can be wrong. This is not
          financial advice.
        </p>
      </main>
    </div>
  )
}
