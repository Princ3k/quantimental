'use client'

import { useCallback, useMemo, useSyncExternalStore } from 'react'

/**
 * Read and write a localStorage key as a React external store.
 *
 * Why `useSyncExternalStore` rather than `useState` + `useEffect`:
 *
 * - localStorage does not exist during server rendering, so the usual pattern
 *   is to render a default, then read storage in an effect and call setState.
 *   That is a cascading render on every mount, and React 19's
 *   `react-hooks/set-state-in-effect` rule flags it.
 * - This hook is the primitive React provides for exactly this situation: a
 *   value that lives outside React, with a separate server snapshot.
 * - It also subscribes to the `storage` event, so changing a value in one tab
 *   updates every other open tab for free.
 */

const listeners = new Set<() => void>()

/** Notify same-tab subscribers; the `storage` event only fires in other tabs. */
function emit() {
  listeners.forEach((listener) => listener())
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  window.addEventListener('storage', onChange)
  return () => {
    listeners.delete(onChange)
    window.removeEventListener('storage', onChange)
  }
}

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    // Private browsing or blocked site data.
    return null
  }
}

function writeRaw(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Persistence is a convenience, never a requirement.
  }
  emit()
}

/**
 * A JSON-serialisable value persisted to localStorage.
 *
 * `parse` must be total: it receives whatever is in storage (possibly corrupt
 * or written by an older version) and must return a usable value or the
 * fallback. It must also return a stable value for identical input, since the
 * result feeds `useSyncExternalStore`'s snapshot comparison.
 */
export function useStoredValue<T>(
  key: string,
  fallback: T,
  parse: (raw: string | null) => T,
): [T, (next: T) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => readRaw(key),
    // Server snapshot: storage is unreachable, so everyone starts at the default.
    () => null,
  )

  // `raw` is a string, so this only recomputes when the stored text changes —
  // which keeps the returned object identity stable across re-renders.
  const value = useMemo(() => {
    try {
      return parse(raw)
    } catch {
      return fallback
    }
    // `parse` and `fallback` are expected to be stable for a given key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw])

  const setValue = useCallback(
    (next: T) => {
      writeRaw(key, JSON.stringify(next))
    },
    [key],
  )

  return [value, setValue]
}
