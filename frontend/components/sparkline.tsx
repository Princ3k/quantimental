'use client'

import { useId } from 'react'

/**
 * A price trend line.
 *
 * Decorative context for the figures beside it, so it is aria-hidden — the
 * price and change are already in the text. Drawn as a hairline with no fill
 * beyond a faint wash, so a grid of these reads as texture rather than noise.
 */
export function Sparkline({
  data,
  height = 38,
  className,
}: {
  data: number[]
  height?: number
  className?: string
}) {
  const gradientId = useId()
  if (data.length < 2) return null

  const width = 100
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min

  const y = (value: number) =>
    range === 0 ? height / 2 : height - ((value - min) / range) * (height - 4) - 2

  const points = data.map((value, i) => [(i / (data.length - 1)) * width, y(value)] as const)
  const line = points.map(([x, py], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${py.toFixed(1)}`).join('')
  const up = data[data.length - 1] >= data[0]
  const stroke = up ? 'var(--up)' : 'var(--down)'

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={{ width: '100%', height }}
      aria-hidden
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.14" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
