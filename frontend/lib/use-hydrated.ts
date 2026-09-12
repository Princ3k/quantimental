'use client'

import { useSyncExternalStore } from 'react'

/* Stable module-level references: recreating these per render would make
   useSyncExternalStore resubscribe on every pass. Hydration happens once and
   never changes afterwards, so the subscribe function has nothing to do. */
const subscribe = () => () => {}
const onClient = () => true
const onServer = () => false

/**
 * False during server render and the first client pass, true afterwards.
 *
 * For UI that depends on something the server cannot see — localStorage, the
 * user's timezone, whether they follow a stock. Rendering from a client-only
 * source during prerender bakes a guess into static HTML that is then served
 * to everyone; on a stock page that meant shipping "You're following AAPL" to
 * readers who follow nothing.
 *
 * Implemented with useSyncExternalStore rather than an effect that calls
 * setState: the effect version works, but it schedules a second render pass on
 * every mount and React's lint rules reject it for that reason.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(subscribe, onClient, onServer)
}
