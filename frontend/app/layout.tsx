import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'

import { ThemeProvider, THEME_STORAGE_KEY } from '@/components/theme-provider'
import './globals.css'

export const metadata: Metadata = {
  title: 'Quantimental — Stock signals in plain English',
  description:
    'Technical analysis and market sentiment, combined into a single clear verdict and explained in ordinary words.',
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#fafafa' },
    { media: '(prefers-color-scheme: dark)', color: '#1a1a20' },
  ],
}

/*
 * Runs before first paint so the correct theme class is already on <html>.
 * Without it the page renders light, then snaps to dark once React hydrates —
 * a visible flash on every load for dark-mode users.
 */
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="antialiased">
        <ThemeProvider>{children}</ThemeProvider>
        <Analytics />
      </body>
    </html>
  )
}
