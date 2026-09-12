/**
 * The daily snapshot of every stock the scan measures.
 *
 * One static file carrying all 503 S&P constituents, published by the same
 * GitHub Action that produces the unusual feed. It exists so that anything
 * needing *a particular* stock's numbers — a per-stock page, a home-screen
 * widget — can have them without an API call.
 *
 * That matters more than it sounds. A page for AAPL needs AAPL's numbers
 * whether or not AAPL had an interesting day, and 503 pages fetching them from
 * our own API would put an unauthenticated request behind every page view and
 * every crawl. Instead: 19 KB gzipped, served from a CDN, cached by Next.
 *
 * Keys are short because this carries 503 rows; the published file documents
 * them in its own `fields` block.
 */

const SOURCE =
  process.env.NEXT_PUBLIC_SNAPSHOT_URL ??
  'https://raw.githubusercontent.com/Princ3k/quantimental/main/public/snapshot.json'

/**
 * How long a fetched snapshot stays warm in Next's data cache.
 *
 * The page's own `export const revalidate` must be a literal — Next statically
 * analyses it — so the stock page repeats 1800 rather than importing this.
 * Keep the two in step.
 */
export const SNAPSHOT_REVALIDATE_SECONDS = 1800

export interface SnapshotStock {
  /** Ticker. */
  t: string
  /** Company name. */
  n: string
  /** GICS sector. */
  s: string
  /** Price. */
  p: number
  /** Change percent today. */
  c: number
  /** Multiple of this stock's typical daily move. */
  x: number
  /** Typical daily move, as a percentage. */
  d: number
  /** Change percent over two weeks. */
  w: number
  /** One-sentence description, written by the backend so wording never forks. */
  h: string
  /** Two-week direction. */
  st: 'rising' | 'falling' | 'steady'
  /**
   * How this move compares to its sector and the market — the difference
   * between "your stock fell" and "everything fell".
   */
  ctx?: string
  /** The market's move today, as the median of the scanned universe. */
  mkt?: number
  /** This sector's move today, as the median of its members. */
  sec?: number
  /** News articles per day. Absent when coverage could not be measured. */
  v?: number
  /**
   * Multiple of this stock's own normal coverage. Absent until the attention
   * archive holds enough history to say — which is the honest answer for its
   * first weeks, and better than a number computed from four observations.
   */
  vx?: number
}

export interface Snapshot {
  as_of: string | null
  generated_at: string
  count: number
  stocks: SnapshotStock[]
}

/**
 * Fetch the snapshot, or null when it is unavailable.
 *
 * Cached by Next for `SNAPSHOT_REVALIDATE_SECONDS`, so 503 pages rendering in
 * the same window share a single fetch rather than making one each.
 */
export async function getSnapshot(): Promise<Snapshot | null> {
  try {
    const response = await fetch(SOURCE, {
      next: { revalidate: SNAPSHOT_REVALIDATE_SECONDS },
    })
    if (!response.ok) return null

    const payload: unknown = await response.json()
    if (
      !payload ||
      typeof payload !== 'object' ||
      !Array.isArray((payload as Snapshot).stocks)
    ) {
      return null
    }
    return payload as Snapshot
  } catch {
    return null
  }
}

/** One stock from the snapshot, matched case-insensitively. */
export async function getSnapshotStock(ticker: string): Promise<SnapshotStock | null> {
  const snapshot = await getSnapshot()
  if (!snapshot) return null

  const wanted = ticker.toUpperCase()
  return snapshot.stocks.find((s) => s.t.toUpperCase() === wanted) ?? null
}

/** The canonical origin, used for absolute URLs in metadata and the sitemap. */
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? 'https://quantimental-sooty.vercel.app'
