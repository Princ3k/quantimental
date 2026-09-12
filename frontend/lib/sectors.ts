import { getSnapshot, type SnapshotStock } from '@/lib/snapshot'

/**
 * Sector views, derived from the snapshot rather than fetched.
 *
 * Every number here already exists: the daily scan measures all 503
 * constituents and each row carries its GICS sector. Grouping them costs one
 * pass over a file the stock pages already read, and answers the question the
 * attribution line on a stock page invites — "my stock fell because its sector
 * fell; so what happened to the sector?"
 */

export interface Sector {
  name: string
  slug: string
  /** Median move of its members. Median, so one collapse is not the sector. */
  change_percent: number
  members: SnapshotStock[]
  /** Members that moved furthest from the sector, in either direction. */
  standouts: SnapshotStock[]
  rising: number
  falling: number
}

/** Sectors with fewer members than this are summarised from too few companies. */
const MIN_MEMBERS = 8

const STANDOUT_COUNT = 5

export function slugify(name: string): string {
  return name.toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

/** Every sector in the latest scan, strongest first. */
export async function getSectors(): Promise<Sector[]> {
  const snapshot = await getSnapshot()
  if (!snapshot) return []

  const grouped = new Map<string, SnapshotStock[]>()
  for (const stock of snapshot.stocks) {
    if (!stock.s) continue
    const existing = grouped.get(stock.s)
    if (existing) existing.push(stock)
    else grouped.set(stock.s, [stock])
  }

  const sectors: Sector[] = []
  for (const [name, members] of grouped) {
    if (members.length < MIN_MEMBERS) continue

    const change = median(members.map((m) => m.c))
    const byDistance = [...members].sort(
      (a, b) => Math.abs(b.c - change) - Math.abs(a.c - change),
    )

    sectors.push({
      name,
      slug: slugify(name),
      change_percent: Number(change.toFixed(2)),
      members: [...members].sort((a, b) => b.c - a.c),
      standouts: byDistance.slice(0, STANDOUT_COUNT),
      rising: members.filter((m) => m.c > 0.5).length,
      falling: members.filter((m) => m.c < -0.5).length,
    })
  }

  return sectors.sort((a, b) => b.change_percent - a.change_percent)
}

export async function getSector(slug: string): Promise<Sector | null> {
  const sectors = await getSectors()
  return sectors.find((s) => s.slug === slug.toLowerCase()) ?? null
}

/** One sentence describing what a sector did. Same voice as the stock pages. */
export function describeSector(sector: Sector): string {
  const direction =
    sector.change_percent > 0.5
      ? `rose ${sector.change_percent.toFixed(1)}%`
      : sector.change_percent < -0.5
        ? `fell ${Math.abs(sector.change_percent).toFixed(1)}%`
        : 'was little changed'

  const total = sector.members.length
  return (
    `${sector.name} ${direction} today, measured as the median of its ` +
    `${total} companies — ${sector.rising} rose and ${sector.falling} fell.`
  )
}
