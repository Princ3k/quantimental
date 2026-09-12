'use client'

import { useTheme } from '@/components/theme-provider'

export function SiteHeader() {
  const { theme, toggleTheme, mounted } = useTheme()

  return (
    <header className="border-rule border-b">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8">
        <span className="font-mono text-[0.9375rem] font-medium tracking-tight">
          Quantimental
        </span>
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
    </header>
  )
}
