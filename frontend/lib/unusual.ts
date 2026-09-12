/**
 * The daily scan of the S&P 500 for stocks having unusual days.
 *
 * Fetched as a **static file**, not from our API. The scan downloads 503
 * tickers and takes around nine seconds, so it runs on a schedule in GitHub
 * Actions and commits the result; this reads that commit. The payload is
 * identical for every viewer and changes only when the market does, which
 * makes it a file rather than a request.
 *
 * Consequences worth knowing: it costs nothing, it never cold-starts, and it
 * stays up even when the API does not. raw.githubusercontent serves it with
 * `Access-Control-Allow-Origin: *` and a 300-second cache.
 */

// Overridable so development can point at a local copy, or a fork at its own
// scan, without editing code.
const SOURCE =
  process.env.NEXT_PUBLIC_UNUSUAL_URL ??
  'https://raw.githubusercontent.com/Princ3k/quantimental/main/public/unusual.json'

export interface UnusualMove {
  ticker: string
  company: string
  sector: string
  price: number
  change_percent: number
  /** This stock's own average daily range, as a percentage. */
  typical_percent: number
  /** How many times its normal daily move today's move is. */
  multiple: number
  direction: 'up' | 'down'
  period_percent: number
  /** One ready-to-render sentence. */
  headline: string
}

export interface UnusualScan {
  available: true
  generated_at: string
  /** The session this reflects, which on a weekend is the previous Friday. */
  as_of: string | null
  scanned: number
  universe: number
  unusual_count: number
  rising: number
  falling: number
  /** Stocks that cleared the unusual bar. Empty on a calm day, which is fine. */
  movers: UnusualMove[]
  /** The day's largest moves, always populated. A different claim from `movers`. */
  biggest: UnusualMove[]
  threshold: { multiple: number; min_move_percent: number }
}

/**
 * Fetch the latest scan, or null if it is unavailable.
 *
 * Returns null rather than throwing: this is a supplementary panel, and a
 * GitHub outage should quietly remove it rather than break the dashboard
 * somebody actually came for.
 */
export async function getUnusualScan(signal?: AbortSignal): Promise<UnusualScan | null> {
  try {
    const response = await fetch(SOURCE, { signal, cache: 'no-store' })
    if (!response.ok) return null

    const payload: unknown = await response.json()
    if (
      !payload ||
      typeof payload !== 'object' ||
      !('movers' in payload) ||
      !Array.isArray((payload as UnusualScan).movers)
    ) {
      return null
    }
    return payload as UnusualScan
  } catch {
    return null
  }
}
