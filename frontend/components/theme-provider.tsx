'use client'

import { useCallback, useSyncExternalStore } from 'react'

type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'quantimental.theme'

const listeners = new Set<() => void>()

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  window.addEventListener('storage', onChange)
  return () => {
    listeners.delete(onChange)
    window.removeEventListener('storage', onChange)
  }
}

/**
 * The live theme, read from the class the inline head script already applied.
 *
 * That script runs before first paint, so there is never a flash of the wrong
 * theme. This hook only reflects the current state and handles changes.
 */
function getSnapshot(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/** During server rendering nothing is known; light is the documented default. */
function getServerSnapshot(): Theme {
  return 'light'
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  // True once the client has taken over. Theme-dependent UI (like a sun/moon
  // icon) gates on this so server and client markup agree on first render.
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )

  const setTheme = useCallback((next: Theme) => {
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // Storage can be unavailable in private browsing; the theme still
      // applies for this session.
    }
    listeners.forEach((listener) => listener())
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(getSnapshot() === 'dark' ? 'light' : 'dark')
  }, [setTheme])

  return { theme, setTheme, toggleTheme, mounted }
}

/**
 * Kept as a component so the app tree reads clearly and a future migration to
 * a context-based provider does not require touching every consumer. The
 * theme itself lives in the DOM, not in React state.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
