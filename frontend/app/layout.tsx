import type { Metadata, Viewport } from 'next'

import { SITE_URL } from '@/lib/snapshot'
import { Inter_Tight, JetBrains_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'

import { ThemeProvider } from '@/components/theme-provider'
import { THEME_STORAGE_KEY } from '@/lib/theme'
import './globals.css'

/*
 * Inter Tight for text and JetBrains Mono for figures.
 *
 * Tight rather than plain Inter: the narrower set and closer default tracking
 * suit large headline numbers, which is most of this interface. JetBrains Mono
 * has genuine tabular figures, so a price updating from 99.99 to 100.00 does
 * not shift the layout.
 */
const sans = Inter_Tight({
  subsets: ['latin'],
  variable: '--font-inter-tight',
  display: 'swap',
})

const mono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  // Required for the per-stock pages to emit absolute og:image and canonical
  // URLs. Without it Next warns and emits relative ones, which most link
  // previewers silently refuse to resolve.
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Quantimental',
    // Stock pages supply their own name; this keeps the brand on the end.
    template: '%s · Quantimental',
  },
  description:
    'What the market is doing today, and what it means for the stocks you follow — in plain English.',
  openGraph: {
    siteName: 'Quantimental',
    type: 'website',
  },
  // Without this X renders the share card as a small square thumbnail and
  // crops the sentence out of it, which is the only part worth reading.
  twitter: {
    card: 'summary_large_image',
  },
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#fafaf9' },
    { media: '(prefers-color-scheme: dark)', color: '#1c1b1a' },
  ],
}

/* Runs before first paint so there is no flash of the wrong theme. */

// This shipped broken once: the key was imported from a client module, Next
// swapped it for a throwing stub on the server, and the template literal
// stringified the stub into the script without anything complaining. TypeScript
// cannot catch that — the declared type is still `string`. So check the value.
if (typeof THEME_STORAGE_KEY !== 'string') {
  throw new Error(
    'THEME_STORAGE_KEY must be a plain string at render time. Getting anything ' +
      'else means it is being read across the server/client boundary again.',
  )
}

const themeScript = `
(function() {
  try {
    var stored = localStorage.getItem('${THEME_STORAGE_KEY}');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (stored === 'dark' || (!stored && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans">
        <ThemeProvider>{children}</ThemeProvider>
        <Analytics />
      </body>
    </html>
  )
}
