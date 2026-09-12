import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { SiteHeader } from '@/components/site-header'
import { describeSector, getSector, getSectors } from '@/lib/sectors'
import { SITE_URL, type SnapshotStock } from '@/lib/snapshot'
import { cn } from '@/lib/utils'

/**
 * One sector, and what its companies did.
 *
 * This exists because the stock pages invite the question and then leave it
 * hanging: "Information Technology rose 1.9%, so this move tracked the market"
 * tells you the sector is the reason, and nowhere to go to see why. Every
 * number is already in the snapshot — grouping it costs one pass over a file
 * the stock pages already read.
 */

export const revalidate = 1800

export async function generateStaticParams() {
  const sectors = await getSectors()
  return sectors.map((sector) => ({ slug: sector.slug }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const sector = await getSector(slug)
  if (!sector) return { title: 'Sector' }

  const title = `${sector.name} — what's happening`
  const description = describeSector(sector)

  return {
    title,
    description,
    alternates: { canonical: `/sector/${sector.slug}` },
    openGraph: { title, description, url: `${SITE_URL}/sector/${sector.slug}` },
  }
}

export default async function SectorPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const sector = await getSector(slug)
  if (!sector) notFound()

  const up = sector.change_percent >= 0

  return (
    <div className="min-h-screen">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> All stocks
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight">{sector.name}</h1>

        <div className="mt-5 flex items-end gap-4">
          <p
            className={cn(
              'tnum font-mono text-[2.25rem] leading-none font-medium tracking-tight',
              up ? 'text-up' : 'text-down',
            )}
          >
            {up ? '+' : ''}
            {sector.change_percent.toFixed(2)}%
          </p>
          <p className="text-ink-3 pb-1 text-[0.875rem]">median, today</p>
        </div>

        <p className="mt-6 text-[0.9375rem] leading-relaxed text-balance">
          {describeSector(sector)}
        </p>
        <p className="text-ink-3 mt-2 text-[0.875rem] leading-relaxed">
          The median rather than an average, so one company collapsing on an earnings
          miss does not become what the whole sector did.
        </p>

        <section className="rule-t mt-10 pt-8">
          <h2 className="text-lg font-medium tracking-tight">Furthest from the sector</h2>
          <p className="text-ink-3 mt-1.5 text-[0.875rem] leading-relaxed">
            The companies that moved least like their peers today — where a
            sector-wide explanation stops working.
          </p>
          <ul className="mt-5 space-y-2.5">
            {sector.standouts.map((stock) => (
              <Row key={stock.t} stock={stock} sectorMove={sector.change_percent} />
            ))}
          </ul>
        </section>

        <section className="rule-t mt-10 pt-8">
          <h2 className="text-lg font-medium tracking-tight">
            All {sector.members.length} companies
          </h2>
          <ul className="mt-5 space-y-2.5">
            {sector.members.map((stock) => (
              <Row key={stock.t} stock={stock} sectorMove={sector.change_percent} />
            ))}
          </ul>
        </section>

        <p className="text-ink-3 rule-t mt-12 pt-6 text-[0.8125rem] leading-relaxed">
          Describes moves that have already happened. Not a forecast, and{' '}
          <Link href="/method" className="hover:text-ink underline underline-offset-2">
            not advice
          </Link>
          .
        </p>
      </main>
    </div>
  )
}

function Row({ stock, sectorMove }: { stock: SnapshotStock; sectorMove: number }) {
  const up = stock.c >= 0
  const gap = stock.c - sectorMove

  return (
    <li>
      <Link
        href={`/stock/${stock.t.toLowerCase()}`}
        className="hover:bg-surface -mx-2 flex items-baseline gap-3 rounded px-2 py-1.5 transition-colors"
      >
        <span className="font-mono text-[0.8125rem]">{stock.t}</span>
        <span className="text-ink-2 min-w-0 flex-1 truncate text-[0.8125rem]">{stock.n}</span>
        {/* Distance from the sector, which is the column that makes this page
            more than a sorted list of percentages. */}
        <span className="text-ink-3 tnum shrink-0 font-mono text-[0.6875rem]">
          {gap >= 0 ? '+' : ''}
          {gap.toFixed(1)} vs sector
        </span>
        <span
          className={cn('tnum shrink-0 font-mono text-[0.8125rem]', up ? 'text-up' : 'text-down')}
        >
          {up ? '+' : ''}
          {stock.c.toFixed(2)}%
        </span>
      </Link>
    </li>
  )
}
