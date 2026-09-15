/**
 * What the machinery did, as opposed to what the market did.
 *
 * Everything here is already public — the snapshot the site renders, the API's
 * own /health, and the Actions API of a public repository. Nothing touches the
 * attention archive's contents, only the count of sessions it holds, which is
 * the number that tells you whether `vx` is missing because coverage was
 * ordinary or because there is not yet enough history to say.
 *
 * It exists because the alternative was checking four browser tabs and a
 * terminal to answer "did it run".
 */

import { SNAPSHOT_URL } from '@/lib/snapshot'

const HEALTH_URL = `${process.env.NEXT_PUBLIC_API_URL ?? ''}/health`
const RUNS_URL =
  'https://api.github.com/repos/Princ3k/quantimental/actions/runs?per_page=40'

/** Slots each workflow is scheduled for on a weekday, for a coverage figure. */
export const DAILY_SLOTS: Record<string, number> = {
  'Publish Unusual Moves': 9,
  'Publish Signal Desk': 18,
}

interface ErrorReporting {
  configured: boolean
  started: boolean
}

export interface Run {
  name: string
  event: string
  status: string
  conclusion: string | null
  created_at: string
}

export interface Ops {
  snapshot: {
    as_of: string | null
    generated_at: string | null
    count: number
    withCoverage: number
    withFilings: number
    archiveDays: number | null
    archiveNeeded: number | null
  } | null
  health: {
    status: string
    errorReporting: ErrorReporting | null
    sources: Record<string, { configured: boolean; working: boolean | null }>
  } | null
  runs: Run[] | null
}

/** Never throws. A panel that cannot load says so; it does not take the page down. */
async function grab<T>(url: string, revalidate: number): Promise<T | null> {
  try {
    const response = await fetch(url, { next: { revalidate } })
    if (!response.ok) return null
    return (await response.json()) as T
  } catch {
    return null
  }
}

export async function getOps(): Promise<Ops> {
  const [snap, health, runs] = await Promise.all([
    grab<Record<string, unknown>>(SNAPSHOT_URL, 60),
    grab<Record<string, unknown>>(HEALTH_URL, 60),
    grab<{ workflow_runs: Run[] }>(RUNS_URL, 60),
  ])

  const stocks = (snap?.stocks as Record<string, unknown>[] | undefined) ?? []
  const subsystems = (health?.subsystems ?? {}) as Record<string, unknown>
  const sentiment = (subsystems.sentiment ?? {}) as Record<string, unknown>

  return {
    snapshot: snap
      ? {
          as_of: (snap.as_of as string) ?? null,
          generated_at: (snap.generated_at as string) ?? null,
          count: (snap.count as number) ?? stocks.length,
          withCoverage: stocks.filter((s) => s.v !== undefined).length,
          withFilings: stocks.filter((s) => s.f !== undefined).length,
          archiveDays: (snap.archive_days as number) ?? null,
          archiveNeeded: (snap.archive_days_needed as number) ?? null,
        }
      : null,
    health: health
      ? {
          status: (health.status as string) ?? 'unknown',
          errorReporting:
            (subsystems.error_reporting as ErrorReporting | undefined) ?? null,
          sources: Object.fromEntries(
            Object.entries(sentiment).filter(
              ([, v]) => v && typeof v === 'object' && 'configured' in (v as object),
            ) as [string, { configured: boolean; working: boolean | null }][],
          ),
        }
      : null,
    runs: runs?.workflow_runs ?? null,
  }
}

/** Minutes since an ISO timestamp, or null when it cannot be read. */
export function minutesSince(iso: string | null): number | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  return Math.max(0, Math.round((Date.now() - then) / 60_000))
}

export function describeAge(minutes: number | null): string {
  if (minutes === null) return 'unknown'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
