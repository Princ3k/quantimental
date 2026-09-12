import type { Metadata } from 'next'
import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'

/**
 * Terms, kept to what actually applies.
 *
 * The section that matters is the first one. Everything a tool like this
 * publishes is information about securities, and the line between that and
 * investment advice is the one thing here with real consequences — so it is
 * stated at the top in plain words rather than buried in capitals halfway
 * down, where nobody has ever read it.
 */
export const metadata: Metadata = {
  title: 'Terms',
  description: 'The terms of using Quantimental, including what it is not.',
  alternates: { canonical: '/terms' },
}

export default function TermsPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> Back
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight">Terms</h1>
        <p className="text-ink-3 mt-2 text-[0.875rem]">Last updated 12 September 2026</p>

        <div className="mt-8 space-y-8">
          <Section title="This is not financial advice">
            <p>
              Quantimental describes what has already happened to publicly traded companies.
              It is information, not advice, and nothing on it is a recommendation to buy,
              sell or hold anything.
            </p>
            <p>
              We are not a broker, a registered investment adviser, or licensed to give
              financial advice in any jurisdiction. We do not know your circumstances, your
              goals, your tax position or your tolerance for loss, and nothing here is
              tailored to them. Before acting on anything you read here, speak to someone
              qualified who does know those things.
            </p>
            <p>
              The app deliberately does not forecast prices.{' '}
              <Link href="/method" className="text-ink underline underline-offset-2">
                We measured our own attempt at that and published the result
              </Link>
              , which is the most useful thing we can tell you about how much to trust it.
            </p>
          </Section>

          <Section title="The data can be wrong">
            <p>
              Prices, news and discussion come from third parties — Yahoo Finance, Reddit and
              MarketAux. Data can be delayed, incomplete, misattributed or simply incorrect,
              and we do not independently verify it. Prices are not real-time and should
              never be treated as a quote you could trade on.
            </p>
            <p>
              Where a source fails, the app says so rather than filling the gap with a
              plausible number. But we cannot detect every kind of bad data, and some will
              get through.
            </p>
          </Section>

          <Section title="Availability">
            <p>
              This runs on free and low-cost infrastructure. It may be slow, rate-limited, or
              unavailable without notice, and we make no commitment to keep it running. Do
              not build anything you care about on top of it.
            </p>
          </Section>

          <Section title="Acceptable use">
            <p>
              Use it for yourself. Do not scrape it, run automated requests against the API,
              or republish its output as your own. Automated traffic is rate-limited because
              every lookup costs us a request to an upstream provider with a daily quota.
            </p>
          </Section>

          <Section title="Liability">
            <p>
              Quantimental is provided as is, without warranty of any kind. To the fullest
              extent the law allows, we are not liable for any loss arising from your use of
              it — including investment losses, lost profits, or decisions made on the basis
              of anything published here.
            </p>
            <p>
              Nothing in these terms limits liability that cannot be limited by law.
            </p>
          </Section>

          <Section title="The code is public">
            <p>
              Everything described here can be checked:{' '}
              <a
                href="https://github.com/Princ3k/quantimental"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-ink underline underline-offset-2"
              >
                github.com/Princ3k/quantimental
              </a>
              . If the app and these terms ever disagree, the code is the honest account and
              we would like to know.
            </p>
          </Section>
        </div>

        <p className="text-ink-3 rule-t mt-12 pt-6 text-[0.8125rem]">
          See also{' '}
          <Link href="/privacy" className="hover:text-ink underline underline-offset-2">
            Privacy
          </Link>
          .
        </p>
      </main>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-[1.0625rem] font-medium tracking-tight">{title}</h2>
      <div className="text-ink-2 mt-2.5 space-y-3 text-[0.9375rem] leading-relaxed">
        {children}
      </div>
    </section>
  )
}
