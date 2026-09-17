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
              <p className="text-ink-3 text-[0.8125rem]">{sector.members.length} companies</p>
            </div>

            {/* Company name as the link text, not the ticker. Somebody
                searching arrives with a name in mind, and it is the name that
                tells a crawler what the page is about. */}
            <ul className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {[...sector.members]
                .sort((a, b) => a.n.localeCompare(b.n))
                .map((stock) => (
                  <li key={stock.t} className="text-[0.875rem]">
                    <Link
                      href={`/stock/${stock.t.toLowerCase()}`}
                      className="hover:text-ink-2 transition-colors"
                    >
                      {stock.n}
                      <span className="text-ink-3 ml-1.5 font-mono text-[0.75rem]">{stock.t}</span>
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
