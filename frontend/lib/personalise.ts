/**
 * Connect the market-wide read to the stocks a person actually holds.
 *
 * "Energy led this week" is a newsletter. "Energy led, which is why XOM is
 * your best performer" is a product. Same facts, but the second one answers
 * the question the reader actually arrived with.
 *
 * Computed on the client from data already fetched — no extra request, no LLM
 * call, and nothing is claimed that the numbers do not already show.
 */

import type { SectorSummary, StockSignal } from './types'

/** Sector ETF names as the backend reports them, mapped to yfinance sectors. */
const SECTOR_ALIASES: Record<string, string[]> = {
  Technology: ['Technology'],
  Financials: ['Financial Services', 'Financials'],
  Energy: ['Energy'],
  'Health Care': ['Healthcare', 'Health Care'],
  Industrials: ['Industrials'],
  'Consumer Discretionary': ['Consumer Cyclical', 'Consumer Discretionary'],
  'Consumer Staples': ['Consumer Defensive', 'Consumer Staples'],
  Utilities: ['Utilities'],
  Materials: ['Basic Materials', 'Materials'],
  Communications: ['Communication Services', 'Communications'],
}

function matches(sectorName: string, stockSector: string | null): boolean {
  if (!stockSector) return false
  const aliases = SECTOR_ALIASES[sectorName] ?? [sectorName]
  return aliases.some((alias) => alias.toLowerCase() === stockSector.toLowerCase())
}

/**
 * One sentence tying sector leadership to the user's holdings, or null.
 *
 * Returns null rather than reaching for something to say: a line that fires
 * every day regardless of whether it is relevant stops being read.
 */
export function personalNote(
  signals: StockSignal[],
  sectors: SectorSummary | undefined,
): string | null {
  if (!sectors?.available || signals.length === 0) return null

  const leader = sectors.leaders?.[0]
  const laggard = sectors.laggards?.[0]

  // Only worth saying when the spread is real.
  if (leader && leader.change_percent > 1) {
    const held = signals.filter((s) => matches(leader.name, s.sector))
    if (held.length > 0) {
      const names = held.slice(0, 3).map((s) => s.ticker).join(', ')
      return `${leader.name} led the market this week, which is showing up in your ${names}.`
    }
  }

  if (laggard && laggard.change_percent < -1) {
    const held = signals.filter((s) => matches(laggard.name, s.sector))
    if (held.length > 0) {
      const names = held.slice(0, 3).map((s) => s.ticker).join(', ')
      return `${laggard.name} was the weakest sector this week, which is weighing on your ${names}.`
    }
  }

  // Nothing the user holds sat at either end — say so rather than inventing a link.
  const sectorsHeld = new Set(signals.map((s) => s.sector).filter(Boolean))
  if (sectorsHeld.size > 0 && leader && !signals.some((s) => matches(leader.name, s.sector))) {
    return `None of your stocks are in ${leader.name}, this week's strongest sector.`
  }

  return null
}
