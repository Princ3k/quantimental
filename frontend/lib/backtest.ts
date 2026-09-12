/**
 * The backtest that ended the buy/sell verdicts.
 *
 * Published as a static file by `backend/scripts/backtest.py --json`, and read
 * here so the claim on the method page is the measurement rather than a
 * remembered summary of it. The two drifted apart once already: the site said
 * "1,888 readings, none significant" while the actual five-year run found
 * 3,792 observations and two significant buckets pointing the wrong way.
 */

const SOURCE =
  process.env.NEXT_PUBLIC_BACKTEST_URL ??
  'https://raw.githubusercontent.com/Princ3k/quantimental/main/public/backtest.json'

export type VerdictAction = 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell'

export interface BacktestBucket {
  action: VerdictAction
  count: number
  mean_return: number
  median_return: number
  /** Null for `hold`, which makes no directional call. */
  hit_rate: number | null
  edge_vs_baseline: number
  std_error: number
  significant: boolean
  t_stat: number | null
}

export interface Backtest {
  generated_at: string
  universe: string[]
  period: { start: string | null; end: string | null }
  observations: number
  horizon_days: number
  rebalance_days: number
  /** What simply holding these names returned over the same windows. */
  baseline_return: number
  /** Share of directional calls that were right. A coin flip is ~50%. */
  directional_accuracy: number | null
  buckets: BacktestBucket[]
  any_significant: boolean
  limitations: string[]
}

export async function getBacktest(): Promise<Backtest | null> {
  try {
    const response = await fetch(SOURCE, { next: { revalidate: 86_400 } })
    if (!response.ok) return null

    const payload: unknown = await response.json()
    if (
      !payload ||
      typeof payload !== 'object' ||
      !Array.isArray((payload as Backtest).buckets)
    ) {
      return null
    }
    return payload as Backtest
  } catch {
    return null
  }
}

export const VERDICT_LABEL: Record<VerdictAction, string> = {
  strong_buy: 'Strong buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong sell',
}
