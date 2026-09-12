import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'

export default function NotFound() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-md px-5 py-24 sm:px-8">
        <h1 className="text-xl font-medium tracking-tight">We couldn&rsquo;t find that page.</h1>
        <p className="text-ink-2 mt-3 text-[0.9375rem] leading-relaxed">
          If you were after a stock, search for it by ticker or company name — we cover every
          market Yahoo Finance does, not just the US.
        </p>
        <Link
          href="/"
          className="text-ink-3 hover:text-ink mt-6 inline-block text-[0.8125rem] transition-colors"
        >
          <span aria-hidden>←</span> Back to your stocks
        </Link>
      </main>
    </div>
  )
}
