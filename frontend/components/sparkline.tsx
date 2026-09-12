'use client'

import { useId } from 'react'

interface SparklineProps {
  /** Closing prices, oldest first. */
  data: number[]
  className?: string
  height?: number
}

/**
 * A small price trend line.
 *
 * Purely decorative context for the numbers beside it, so it is marked
 * aria-hidden — a screen reader gets the price and change from the card text
 * rather than an unreadable path.
 */
export function Sparkline({ data, className, height = 40 }: SparklineProps) {
  const gradientId = useId()

  if (data.length < 2) return null

  const width = 120
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min

  // A perfectly flat series would divide by zero; draw it down the middle.
  const yFor = (value: number) =>
    range === 0 ? height / 2 : height - ((value - min) / range) * (height - 4) - 2

  const points = data.map((value, index) => ({
    x: (index / (data.length - 1)) * width,
    y: yFor(value),
  }))

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const area = `${line} L${width},${height} L0,${height} Z`

  const isPositive = data[data.length - 1] >= data[0]
  const stroke = isPositive ? 'var(--positive)' : 'var(--negative)'

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      className={className}
      aria-hidden
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
