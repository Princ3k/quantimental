import { ImageResponse } from 'next/og'

import { getSnapshotStock } from '@/lib/snapshot'

/**
 * The card people see when a stock page is pasted into a message.
 *
 * It leads with the same sentence the page does, because that sentence is the
 * product. A card showing only a logo and a ticker gives the reader nothing to
 * decide on; one that says "Apple is up 1.8% today, and up 5.6% over the past
 * two weeks" is the reason someone taps it.
 */
export const alt = 'What this stock is doing today'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

// Matches the app's dark theme, resolved to hex — the OG renderer has no CSS
// custom properties and does not understand oklch().
const BG = '#1c1b1a'
const INK = '#f4f3f1'
const INK_2 = '#b0aca6'
const INK_3 = '#7d7a76'
const UP = '#4ec08a'
const DOWN = '#ef7361'

export default async function Image({
  params,
}: {
  params: Promise<{ ticker: string }>
}) {
  const { ticker } = await params
  const symbol = ticker.toUpperCase()
  const stock = await getSnapshotStock(symbol)

  const up = (stock?.c ?? 0) >= 0
  const accent = up ? UP : DOWN

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          background: BG,
          color: INK,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '72px 80px',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 20 }}>
          <span style={{ fontSize: 44, fontWeight: 600, letterSpacing: '-0.02em' }}>
            {symbol}
          </span>
          {stock && (
            <span style={{ fontSize: 28, color: INK_2 }}>{stock.n}</span>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          {stock && (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 24 }}>
              <span style={{ fontSize: 76, fontWeight: 600, letterSpacing: '-0.03em' }}>
                ${stock.p.toFixed(2)}
              </span>
              <span style={{ fontSize: 38, color: accent }}>
                {up ? '↑' : '↓'} {Math.abs(stock.c).toFixed(2)}%
              </span>
            </div>
          )}

          <div
            style={{
              display: 'flex',
              fontSize: 38,
              lineHeight: 1.35,
              color: INK,
              maxWidth: 1000,
            }}
          >
            {stock?.h ?? `What ${symbol} is doing today, in plain English.`}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 24 }}>
          <div style={{ width: 10, height: 10, borderRadius: 5, background: accent }} />
          <span style={{ color: INK_3 }}>
            Quantimental · describes what happened, never what will
          </span>
        </div>
      </div>
    ),
    size,
  )
}
