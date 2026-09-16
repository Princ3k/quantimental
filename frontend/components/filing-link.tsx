'use client'

import { trackFilingLink } from '@/lib/events'

/**
 * The link to an 8-K on EDGAR, counting the click.
 *
 * A client component because the stock page is server-rendered and cannot
 * carry an onClick — and it tracks from its own props rather than a callback,
 * because functions do not cross the server/client boundary. Keeping it this
 * thin means the page stays server-rendered: the sentence a crawler indexes is
 * still in the HTML and only the anchor hydrates.
 *
 * Worth counting because item 8.01 is a quarter of what companies file and its
 * code says only "another event". For those, the link is the entire answer —
 * so how often anyone takes it is the evidence on whether the filings work
 * earned its keep.
 */
export function FilingLink({
  href,
  ticker,
  items,
  children,
}: {
  href: string
  ticker: string
  items: string[]
  children: React.ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-ink-2 hover:text-ink underline decoration-dotted underline-offset-2 transition-colors"
      // Fires before navigation. The tab opens either way, so a blocked
      // analytics request costs the count and never the click.
      onClick={() => trackFilingLink(ticker, items)}
    >
      {children}
    </a>
  )
}
