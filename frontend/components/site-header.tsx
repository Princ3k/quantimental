'use client'

import { Activity, Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useTheme } from '@/components/theme-provider'

export function SiteHeader() {
  const { theme, toggleTheme, mounted } = useTheme()

  return (
    <header className="border-border bg-card/80 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
            <Activity className="size-4" aria-hidden />
          </span>
          <div className="leading-tight">
            <p className="font-semibold">Quantimental</p>
            <p className="text-muted-foreground hidden text-xs sm:block">
              Stock signals in plain English
            </p>
          </div>
        </div>

        {/* Rendered only after mount: the icon depends on the resolved theme,
            which is not known during server rendering. */}
        {mounted && (
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        )}
      </div>
    </header>
  )
}
