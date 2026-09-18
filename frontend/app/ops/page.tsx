import type { Metadata } from 'next'
import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'
import {
  SCHEDULES,
  describeAge,
  getOps,
  minutesSince,
  publishOverdue,
  slotsDue,
  type Run,
} from '@/lib/ops'
import { sessionLabel } from '@/lib/session'

/* A minute. The point of the page is telling you what just happened, and a
   half-hour cache would answer yesterday's question. */
export const revalidate = 60

export const metadata: Metadata = {
  title: 'Operations',
  description: 'Whether the scans ran, and what they produced.',
  // Not secret, but not a page anyone searching for a stock wants to land on.
  robots: { index: false, follow: false },
}

/* A scan is overdue when it is older than the gap between runs plus the delay
   GitHub is entitled to take. Two hours is generous on an hourly schedule and
   deliberately so: a page that cries wolf gets ignored, and this one only
   earns its place if a red mark means something. */

function Status({ ok, children }: { ok: boolean | null; children: React.ReactNode }) {
  const mark = ok === null ? '·' : ok ? '✓' : '✗'
  const tone = ok === null ? 'text-ink-3' : ok ? 'text-up' : 'text-down'
  return (
    <span className={`${tone} tnum`}>
      <span aria-hidden>{mark}</span> {children}
    </span>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-rule flex items-baseline justify-between gap-6 border-b py-2.5 last:border-0">
      <span className="text-ink-2 text-[0.875rem]">{label}</span>
      <span className="text-right text-[0.875rem]">{children}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-ink-3 mb-1 font-mono text-[0.75rem] tracking-wide uppercase">
        {title}
      </h2>
      <div>{children}</div>
    </section>
  )
}

/** Runs today, split by what triggered them — the question is who is keeping the site alive. */
function schedulerTally(runs: Run[], name: string) {
  const today = new Date().toISOString().slice(0, 10)
  const mine = runs.filter((r) => r.name === name && r.created_at.startsWith(today))
  const count = (event: string) =>
    mine.filter((r) => r.event === event && r.conclusion === 'success').length
  return { cron: count('schedule'), dispatch: count('workflow_dispatch') }
}

export default async function OpsPage() {
  const { snapshot, health, runs } = await getOps()

  const publishes = (runs ?? []).filter((r) => r.name.startsWith('Publish'))
  const lastPublish = publishes[0] ?? null
  const age = minutesSince(lastPublish?.created_at ?? null)
  // Overdue is judged against whether a scan was due, not against the clock —
  // see publishOverdue. This row was red every night against current data.
  const overdue = publishOverdue(age)
  const fresh = overdue === null ? null : !overdue
  const failures = publishes.filter((r) => r.conclusion === 'failure').length

  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> All stocks
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight">Operations</h1>
        <p className="text-ink-2 mt-2 text-[0.9375rem] leading-relaxed">
          Whether the machinery ran, and what it produced. Refreshes every minute.
        </p>

        <Section title="Published data">
          {snapshot ? (
            <>
              <Row label="Session described">
                {snapshot.as_of ? sessionLabel(snapshot.as_of) : 'unknown'}
              </Row>
              <Row label="Last publish">
                <Status ok={fresh}>{describeAge(age)}</Status>
              </Row>
              <Row label="Tickers measured">
                <Status ok={snapshot.count >= 500}>{snapshot.count}</Status>
              </Row>
              <Row label="With a coverage reading">
                <Status ok={snapshot.withCoverage === snapshot.count}>
                  {snapshot.withCoverage} / {snapshot.count}
                </Status>
              </Row>
              <Row label="8-K filings attached">{snapshot.withFilings}</Row>
            </>
          ) : (
            <Row label="Snapshot">
              <Status ok={false}>could not be read</Status>
            </Row>
          )}
        </Section>

        <Section title="Attention archive">
          {snapshot?.archiveDays != null && snapshot.archiveNeeded ? (
            <>
              <Row label="Sessions recorded">
                {snapshot.archiveDays} / {snapshot.archiveNeeded} needed
              </Row>
              <Row label="Unusual-coverage figures">
                <Status ok={snapshot.archiveDays >= snapshot.archiveNeeded}>
                  {snapshot.archiveDays >= snapshot.archiveNeeded
                    ? 'live'
                    : `${snapshot.archiveNeeded - snapshot.archiveDays} more sessions`}
                </Status>
              </Row>
            </>
          ) : (
            <Row label="Archive">
              <span className="text-ink-3">not reported by the last scan</span>
            </Row>
          )}
        </Section>

        <Section title="Schedulers">
          {runs ? (
            SCHEDULES.map(({ name, slots }) => {
              const { cron, dispatch } = schedulerTally(runs, name)
              const due = slotsDue(slots)
              // Both schedulers can cover the same slot, so runs can exceed
              // what was due. The figure is coverage of what should have run
              // by now, capped — not a count of runs.
              const covered = Math.min(cron + dispatch, due)
              return (
                <Row key={name} label={name.replace('Publish ', '')}>
                  {due === 0 ? (
                    // Nothing due yet is not nothing working. Before the first
                    // slot of a weekday, and all weekend, there is no coverage
                    // to report and a red mark would be a lie.
                    <span className="text-ink-3">
                      none due yet · {slots.length} today
                    </span>
                  ) : (
                    <span className="tnum">
                      <Status ok={covered >= due}>
                        {covered} / {due} due
                      </Status>
                      <span className="text-ink-3">
                        {' '}
                        · GitHub {cron} · Railway {dispatch}
                      </span>
                    </span>
                  )}
                </Row>
              )
            })
          ) : (
            <Row label="Actions API">
              <span className="text-ink-3">unreachable</span>
            </Row>
          )}
          <Row label="Failed publishes (recent)">
            <Status ok={failures === 0}>{failures}</Status>
          </Row>
        </Section>

        <Section title="API">
          {health ? (
            <>
              <Row label="Service">
                <Status ok={health.status === 'healthy'}>{health.status}</Status>
              </Row>
              <Row label="Error reporting">
                <Status ok={health.errorReporting?.started ?? false}>
                  {health.errorReporting?.started
                    ? 'on'
                    : health.errorReporting?.configured
                      ? 'configured but not started'
                      : 'off'}
                </Status>
              </Row>
              {Object.entries(health.sources).map(([name, source]) => (
                <Row key={name} label={name.replace(/_/g, ' ')}>
                  {/* `working` stays null until something has actually asked.
                      Reporting that as a failure would be the same mistake
                      /health was rewritten to stop making. */}
                  <Status ok={source.working}>
                    {source.working === null
                      ? source.configured
                        ? 'configured, not yet used'
                        : 'not configured'
                      : source.working
                        ? 'working'
                        : 'failing'}
                  </Status>
                </Row>
              ))}
            </>
          ) : (
            <Row label="API">
              <Status ok={false}>unreachable</Status>
            </Row>
          )}
        </Section>

        <p className="text-ink-3 mt-10 text-[0.8125rem] leading-relaxed">
          Everything here is read from the published snapshot, the API&rsquo;s own health
          endpoint, and the Actions API of a public repository. The attention archive is
          reported only as a count of sessions — never its readings.
        </p>
      </main>
    </div>
  )
}
