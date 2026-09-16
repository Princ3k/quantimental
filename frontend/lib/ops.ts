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

/**
 * When each workflow is scheduled, in UTC, mirroring the cron blocks.
 *
 * The times rather than a count, because the useful question is not "how many
 * runs should happen today" but "how many should have happened by now". A page
 * that reports nine missing runs at one in the morning, when the first is not
 * due until the afternoon, is reporting a failure that has not occurred — and
 * a red mark that appears every night is one nobody reads by the end of the
 * week.
 */
export const SCHEDULES: { name: string; slots: { hour: number; minute: number }[] }[] = [
  {
    name: 'Publish Unusual Moves',
    // 13 14-21 * * 1-5, plus 43 21 * * 1-5
    slots: [
      ...Array.from({ length: 8 }, (_, i) => ({ hour: 14 + i, minute: 13 })),
      { hour: 21, minute: 43 },
    ],
  },
  {
    name: 'Publish Signal Desk',
    // 7,37 13-21 * * 1-5
    slots: Array.from({ length: 9 }, (_, i) => [
      { hour: 13 + i, minute: 7 },
      { hour: 13 + i, minute: 37 },
    ]).flat(),
  },
]

/**
 * How long after a slot before its absence counts as missing.
 *
 * GitHub's scheduler has been observed running more than half an hour late,
 * and a run that is merely late is not a run that failed. Marking one missing
 * the instant its minute passes would put a red mark on the page for the few
 * minutes after every slot.
 */
const GRACE_MINUTES = 35

/**
 * Slots that should have produced a run by now, on this UTC day.
 *
 * Zero on a weekend, and zero before the first slot of a weekday — in both
 * cases nothing is due, which is a different statement from nothing ran.
 */
export function slotsDue(
  slots: { hour: number; minute: number }[],
  now: Date = new Date(),
): number {
  const day = now.getUTCDay()
  if (day === 0 || day === 6) return 0

  const minutesNow = now.getUTCHours() * 60 + now.getUTCMinutes()
  return slots.filter((s) => minutesNow >= s.hour * 60 + s.minute + GRACE_MINUTES).length
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
          // Only the per-source records. `sentiment` also carries scalars
          // like `groq_model` and `reddit_credentials`, which are facts about
          // a source rather than sources themselves.
          sources: Object.fromEntries(
            Object.entries(sentiment).filter(
              ([, v]) => v && typeof v === 'object' && 'working' in (v as object),
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
