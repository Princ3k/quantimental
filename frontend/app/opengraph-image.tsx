import { ImageResponse } from 'next/og'

import { getSnapshot } from '@/lib/snapshot'

/**
 * The card people see when the site itself is pasted into a message.
 *
 * Until now there was none, so every share fell back to the favicon and a bare
 * title. It leads with the claim the product is actually built on — it says
 * what happened and refuses to say what comes next — and then backs it with
 * three facts read live from today's snapshot, because a card that quotes real
 * coverage on a real session is doing the same job the site does.
 *
 * Deliberately the same ground, type scale and footer as the per-stock card in
 * stock/[ticker]/opengraph-image.tsx. The two get shared side by side.
 */
export const alt = 'Quantimental — what the market did today, in plain English'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

// Literal, for the same reason the pages state it literally: Next reads this
// statically and cannot follow an imported binding.
export const revalidate = 1800

const BG = '#1c1b1a'
const INK = '#f4f3f1'
const INK_2 = '#b0aca6'
const INK_3 = '#7d7a76'
const RULE = '#332f2c'

/** The market's move today: the median the snapshot already carries, else ours. */
function marketMove(changes: number[], carried?: number): number | null {
  if (typeof carried === 'number') return carried
  if (!changes.length) return null
  const sorted = [...changes].sort((a, b) => a - b)
  const mid = sorted.length >> 1
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

function sessionLabel(asOf: string | null): string | null {
  if (!asOf) return null
  const date = new Date(`${asOf.slice(0, 10)}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

export default async function Image() {
  const snapshot = await getSnapshot()
  const stocks = snapshot?.stocks ?? []

  const move = marketMove(
    stocks.map((s) => s.c),
    stocks.find((s) => typeof s.mkt === 'number')?.mkt,
  )
  const session = sessionLabel(snapshot?.as_of ?? null)

  // Only facts we actually have. A card with an empty slot in it reads as
  // broken; one with two facts instead of three just reads as a card.
  const facts: Array<[string, string]> = []
  if (snapshot?.count) facts.push([`${snapshot.count}`, 'companies covered'])
  if (move !== null) {
    facts.push([
      `${move >= 0 ? '+' : '−'}${Math.abs(move).toFixed(2)}%`,
      'median move',
    ])
  }
  if (session) facts.push([session, 'last session'])

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          {/* Mirrors app/icon.svg. Satori cannot read that file at render
              time, so the geometry is repeated here — change both. */}
          <svg width="46" height="46" viewBox="0 0 32 32">
            <path
              d="M4 23 L10 17.5 L15.5 20.5 L24 11"
              fill="none"
              stroke={INK}
              strokeWidth="3.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="24" cy="11" r="3.2" fill={INK} />
          </svg>
          <span style={{ fontSize: 40, fontWeight: 600, letterSpacing: '-0.02em' }}>
            Quantimental
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 34 }}>
          <div
            style={{
              display: 'flex',
              fontSize: 54,
              fontWeight: 600,
              lineHeight: 1.22,
              letterSpacing: '-0.025em',
              maxWidth: 1000,
            }}
          >
            What the market did today, and what it means for the stocks you
            follow.
          </div>

          {facts.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'stretch', gap: 44 }}>
              {facts.map(([value, label], i) => (
                <div key={label} style={{ display: 'flex', gap: 44 }}>
                  {i > 0 && <div style={{ width: 1, background: RULE }} />}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <span style={{ fontSize: 40, fontWeight: 600 }}>{value}</span>
                    <span style={{ fontSize: 24, color: INK_2 }}>{label}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 24 }}>
          <div style={{ width: 10, height: 10, borderRadius: 5, background: INK_3 }} />
          <span style={{ color: INK_3 }}>
            Describes what happened, never what will
          </span>
        </div>
      </div>
    ),
    size,
  )
}
