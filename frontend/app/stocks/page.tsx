import type { Metadata } from 'next'
import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'
import { getSectors } from '@/lib/sectors'
import { SITE_URL } from '@/lib/snapshot'

/* Rebuilt when the scan does, since it lists whatever the scan covers. */
export const revalidate = 1800

export const metadata: Metadata = {
  title: 'Every company we cover',
  description:
    'All 500-odd S&P companies the daily scan measures, grouped by sector, each with its own page.',
  alternates: { canonical: `${SITE_URL}/stocks` },
  openGraph: { title: 'Every company we cover', url: `${SITE_URL}/stocks` },
}

/**
 * The index.
 *
 * It exists because Search Console reported 515 pages as "Discovered —
 * currently not indexed": Google knew the URLs from the sitemap and had not
 * bothered to crawl them. That is what happens to pages nothing links to.
 *
 * A crawler starting at the homepage could reach six sector pages — the
 * compact strip shows the strongest and weakest three, and which six they are
 * changes daily — and no stock page at all, because the dashboard renders its
 * cards on the client. Every one of the 503 was reachable only from the
 * sitemap, which is a hint rather than a path.
 *
 * So: one page, one hop from home, linking every sector and every company. It
 * is also the page the "All stocks" wording has been promising since the stock
 * pages were built.
 */
/** At least twice its own typical day. Matches the dashboard's unusual feed. */
const UNUSUAL_MOVE = 2

function signed(percent: number): string {
  return `${percent > 0 ? '+' : ''}${percent.toFixed(2)}%`
}

function toneOf(percent: number): string {
  if (percent > 0.05) return 'text-up'
  if (percent < -0.05) return 'text-down'
  // Flat is not a direction. Colouring a 0.01% move green says something the
  // number does not.
  return 'text-ink-3'
}

export default async function StocksPage() {
  const sectors = await getSectors()
  const total = sectors.reduce((n, s) => n + s.members.length, 0)

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> Your stocks
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight">Every company we cover</h1>
        <p className="text-ink-2 mt-2 text-[0.9375rem] leading-relaxed">
          {total} companies across {sectors.length} sectors, measured after every close. Each has a
          page describing what it did and whether that was unusual for it.
        </p>
        <p className="text-ink-3 mt-2 text-[0.8125rem] leading-relaxed">
          Today&rsquo;s move and the last two weeks are shown against each name. A dot marks a
          company whose move today was at least twice its own typical day &mdash; which is not the
          same as a big move, and is the only thing here worth a second look.
        </p>

        <nav aria-label="Sectors" className="mt-8 flex flex-wrap gap-x-4 gap-y-2">
          {sectors.map((sector) => (
            <Link
              key={sector.slug}
              href={`#${sector.slug}`}
              className="text-ink-2 hover:text-ink text-[0.8125rem] transition-colors"
            >
              {sector.name}
            </Link>
          ))}
        </nav>

        {sectors.map((sector) => (
          <section key={sector.slug} id={sector.slug} className="rule-t mt-10 pt-6">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-lg font-medium tracking-tight">
                <Link href={`/sector/${sector.slug}`} className="hover:text-ink-2 transition-colors">
                  {sector.name}
                </Link>
              </h2>
              {/* The sector's own median, so a reader can tell a company that
                  moved from a company that was carried. */}
              <p className="text-ink-3 tnum text-[0.8125rem]">
                {sector.members.length} companies &middot;{' '}
                <span className={toneOf(sector.change_percent)}>
                  {signed(sector.change_percent)} median
                </span>
              </p>
            </div>

            {/* Company name as the link text, not the ticker. Somebody
                searching arrives with a name in mind, and it is the name that
                tells a crawler what the page is about.

                Alphabetical, not sorted by move. This is the index — people
                arrive looking for a particular company, and a list that
                reorders itself every afternoon cannot be scanned for one. */}
            <ul className="border-rule/60 mt-4 divide-y">
              {[...sector.members]
                .sort((a, b) => a.n.localeCompare(b.n))
                .map((stock) => (
                  <li key={stock.t}>
                    <Link
                      href={`/stock/${stock.t.toLowerCase()}`}
                      className="hover:bg-rule/20 grid grid-cols-[1fr_auto] items-baseline gap-x-4 rounded px-1 py-2 transition-colors sm:grid-cols-[1fr_5.5rem_6.5rem]"
                    >
                      <span className="min-w-0 text-[0.875rem]">
                        <span className="truncate">{stock.n}</span>
                        <span className="text-ink-3 ml-1.5 font-mono text-[0.75rem]">
                          {stock.t}
                        </span>
                        {stock.x >= UNUSUAL_MOVE && (
                          <span
                            className="text-ink-2 ml-1.5 text-[0.75rem]"
                            title={`Moved ${stock.x}× its typical day`}
                          >
                            &bull;
                          </span>
                        )}
                      </span>
                      <span className={`tnum text-right text-[0.8125rem] ${toneOf(stock.c)}`}>
                        {signed(stock.c)}
                      </span>
                      {/* Hidden on phones: two numbers per row is as much as
                          that width carries before the name starts truncating. */}
                      <span className="text-ink-3 tnum hidden text-right text-[0.8125rem] sm:block">
                        {signed(stock.w)} 2w
                      </span>
                    </Link>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </main>
    </div>
  )
}
