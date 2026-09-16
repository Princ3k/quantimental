/**
 * The four things worth counting.
 *
 * Three days and seventy-eight visitors told us they arrived and left, and
 * nothing about whether the thing worked. These are the questions page views
 * cannot answer: did anyone look a company up, did anyone use the sentiment the
 * launch post advertised, did anyone build a watchlist, did anyone care enough
 * about a filing to go and read it.
 *
 * Anonymous counters only. No identifiers, no personal data, nothing that could
 * be joined back to a person — the product's position is that it stores nothing
 * about you, and instrumentation is not an exception to that. A ticker symbol
 * is a fact about a company, so it travels; anything about the reader does not.
 */

import { track } from '@vercel/analytics'

/** Where a stock was added from — the two paths differ in what they imply. */
export type FollowSource = 'search' | 'unusual-feed'

/** A company was looked up by symbol or name. */
export function trackSearch(ticker: string): void {
  track('search', { ticker: ticker.toUpperCase() })
}

/**
 * A stock was added to the watchlist.
 *
 * The closest thing to a retention signal this product has. There are no
 * accounts, so a returning reader is invisible; someone bothering to build a
 * list is the one act that says they intend to come back.
 */
export function trackFollow(ticker: string, source: FollowSource): void {
  track('follow', { ticker: ticker.toUpperCase(), source })
}

/**
 * Someone asked for news and social sentiment on a stock.
 *
 * The feature the launch post led with, and the one nobody sees unless they
 * press something. If this stays near zero, the post was advertising a button
 * people do not find.
 */
export function trackDeepDive(ticker: string): void {
  track('deep_dive', { ticker: ticker.toUpperCase() })
}

/**
 * Someone opened the 8-K on EDGAR.
 *
 * The only evidence available on whether the filings work earns its keep. Item
 * 8.01 says "another event" and nothing more, so the link is the whole answer
 * for a quarter of filings — this counts how often anyone takes it.
 */
export function trackFilingLink(ticker: string, items: string[]): void {
  track('filing_link', { ticker: ticker.toUpperCase(), item: items[0] ?? 'unknown' })
}
