import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { SiteHeader } from '@/components/site-header'
import { StockDetail } from '@/components/stock-detail'
import { SITE_URL, getSnapshot, getSnapshotStock } from '@/lib/snapshot'

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
  const up = (stock?.c ?? 0) >= 0

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
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
              {stock.s && <span className="text-ink-3"> · {stock.s}</span>}
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

            {/* The sentence. Present in the HTML before any script runs, which
                is what a crawler indexes and a shared link previews. */}
            <p className="mt-7 text-lg leading-relaxed text-balance">{stock.h}</p>

            <p className="text-ink-3 mt-3 text-[0.875rem] leading-relaxed">
              That is {stock.x.toFixed(1)}× this stock&rsquo;s typical{' '}
              {stock.d.toFixed(1)}% daily move
              {stock.x >= 2 ? ' — an unusually large day for it.' : '.'}
            </p>
          </>
        ) : (
          <p className="text-ink-2 mt-7 text-lg leading-relaxed">
            {symbol} is not in our daily scan of the S&amp;P 500, so there is no
            saved reading for it. We can still analyse it live.
          </p>
        )}

        {/* Everything below needs the API, so it loads client-side. Crawlers
            index the static half above and never hit our server. */}
        <StockDetail ticker={symbol} />

        <p className="text-ink-3 rule-t mt-12 pt-6 text-[0.8125rem] leading-relaxed">
          Quantimental describes moves that have already happened, using public
          price data and public news. It cannot predict the future, does not know
          your circumstances, and can be wrong. This is not financial advice.
        </p>
      </main>
    </div>
  )
}
