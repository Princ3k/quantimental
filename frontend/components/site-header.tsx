'use client'

import Link from 'next/link'

import { useTheme } from '@/components/theme-provider'

/**
 * Cryptomental, the sibling site: same approach applied to Base tokens.
 *
 * A plain anchor rather than a Next `Link` — it is a different application on
 * a different subdomain, and routing cannot prefetch across that boundary.
 * It also deliberately does not open a new tab: this is a switch between two
 * products, not a reference to an outside page, and a switcher that leaves the
 * old page behind you is the one that behaves like a switcher.
 */
const CRYPTO_URL = 'https://crypto.thequantimental.com'

export function SiteHeader() {
  const { theme, toggleTheme, mounted } = useTheme()

  return (
    <header className="border-rule border-b">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8">
        {/* The wordmark is the way back. Every page below the dashboard —
            a stock, a sector, the method page — is reached from it, so the
            one thing every reader tries first has to work. */}
        <Link
          href="/"
          className="hover:text-ink-2 font-mono text-[0.9375rem] font-medium tracking-tight transition-colors"
        >
          Quantimental
        </Link>

        {/* Both of these are controls rather than content, so they sit
            together and stay quieter than the wordmark. */}
        <div className="flex items-center gap-3 sm:gap-4">
          <a
            href={CRYPTO_URL}
            className="text-ink-3 hover:text-ink rounded text-[0.8125rem] transition-colors"
          >
            Crypto
          </a>
          {mounted && (
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              className="text-ink-3 hover:text-ink rounded p-1 text-sm transition-colors"
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
