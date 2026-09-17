import type { Metadata } from 'next'
import Link from 'next/link'

import { SiteHeader } from '@/components/site-header'
import { SITE_URL } from '@/lib/snapshot'

/**
 * What we collect, which is very little, said plainly.
 *
 * Written from what the code actually does rather than from a template: the
 * watchlist is localStorage, there are no accounts, and the only third party
 * receiving anything is Vercel Analytics. A policy that claims more than the
 * app does is worse than none, because it is a false statement about people's
 * data rather than a missing one.
 *
 * The Discord section is the exception that proves the rule: the bot does keep
 * a watchlist on our server, which directly contradicts the section above it,
 * so the two sit next to each other rather than the difference being buried.
 * The claim that removing the bot deletes the data is backed by
 * `bot/main.py`'s on_guild_remove — it was written because this page says so.
 */
export const metadata: Metadata = {
  title: 'Privacy',
  description: 'What Quantimental collects, and what it does not.',
  alternates: { canonical: '/privacy' },
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-5 py-12 sm:px-8 sm:py-16">
        <Link href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          <span aria-hidden>←</span> Back
        </Link>

        <h1 className="mt-6 text-2xl font-medium tracking-tight">Privacy</h1>
        <p className="text-ink-3 mt-2 text-[0.875rem]">Last updated 17 September 2026</p>

        <div className="mt-8 space-y-8">
          <Section title="There are no accounts">
            <p>
              You cannot sign up, and we never ask for your name, email address or anything
              else that identifies you. There is nothing to log in to.
            </p>
          </Section>

          <Section title="Your watchlist stays in your browser">
            <p>
              The stocks you follow, your theme preference, and which changes you have
              already seen are stored in your browser&rsquo;s local storage. They are never
              sent to us and never leave your device. Clearing your browser data erases them,
              and they do not follow you to another device — because we have no way to
              connect the two.
            </p>
          </Section>

          <Section title="The Discord bot works differently">
            <p>
              Everything above describes the website. If your server uses our Discord
              bot, there is no browser involved, so its watchlist is kept on our server
              instead. That is the one place we store something for you rather than
              beside you.
            </p>
            <p>
              For each server we keep three things: the tickers it follows, the channel
              its daily post goes to, and which trading session it was last sent. That is
              the whole record.
            </p>
            <p>
              We do not store who used a command. No user IDs, no usernames, no message
              content, and the bot never asks Discord for permission to read your
              messages or your member list — it can only see the commands addressed to
              it. If someone asks for a ticker outside the S&amp;P 500, we record the
              ticker so we know what is worth covering, alongside a one-way hash of the
              server&rsquo;s ID. That tells us how many distinct servers wanted it and
              cannot be turned back into which ones.
            </p>
            <p>
              Removing the bot from a server deletes its watchlist, channel and posting
              history immediately. The anonymous record that some server once asked about
              a ticker stays, because there is nothing in it to connect back to you.
            </p>
          </Section>

          <Section title="What our server sees">
            <p>
              When a page loads market data, our API receives the request: the stock symbols
              being looked up, your IP address, and the usual request headers your browser
              sends to any website.
            </p>
            <p>
              We keep a short-lived count per IP address, in memory, to stop automated
              scripts from exhausting the free data quotas this runs on. It holds a number,
              not a history of what you looked at, and it is discarded after an hour of
              inactivity. We do not write request logs to permanent storage.
            </p>
          </Section>

          <Section title="Analytics">
            <p>
              We use{' '}
              <a
                href="https://vercel.com/docs/analytics/privacy-policy"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-ink underline underline-offset-2"
              >
                Vercel Web Analytics
              </a>
              , which counts page views and where visitors arrived from. It does not use
              cookies, does not follow you across other websites, and does not build a
              profile of you. We use it to find out whether anyone is using this at all.
            </p>
          </Section>

          <Section title="Where the data comes from">
            <p>
              Prices and company news come from Yahoo Finance, discussion from Reddit&rsquo;s
              public feeds, and additional news from MarketAux. Requests to those services
              are made by our server, not your browser, so they do not see your IP address.
              Following a link to an article takes you to that publisher&rsquo;s own site,
              under their terms.
            </p>
          </Section>

          <Section title="Your rights">
            <p>
              Because we hold no account and no identifier for you, there is no personal
              profile to export, correct or delete. To remove everything this site has stored
              about you, clear its site data in your browser.
            </p>
            <p>
              If you have a question about any of this, the whole project is open source and
              you are welcome to check the code:{' '}
              <a
                href="https://github.com/Princ3k/quantimental"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-ink underline underline-offset-2"
              >
                github.com/Princ3k/quantimental
              </a>
              .
            </p>
          </Section>

          <Section title="Changes">
            <p>
              If this changes, the date at the top changes with it. The full history of this
              page is in the repository above.
            </p>
          </Section>
        </div>

        <p className="text-ink-3 rule-t mt-12 pt-6 text-[0.8125rem]">
          See also{' '}
          <Link href="/terms" className="hover:text-ink underline underline-offset-2">
            Terms
          </Link>{' '}
          and{' '}
          <Link href="/method" className="hover:text-ink underline underline-offset-2">
            why we don&rsquo;t predict
          </Link>
          . Canonical URL: {SITE_URL}/privacy
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
