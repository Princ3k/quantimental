'use client'

import { useEffect } from 'react'

/**
 * What a visitor sees when a page crashes.
 *
 * Without this file a render error is a blank white screen — React unmounts
 * the tree and Next has nothing to put in its place. The difference between
 * "this is broken, here is a way out" and an empty page is the difference
 * between a bug and a lost visitor.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // The digest is the only handle on the server-side stack, which is not
    // sent to the browser. Without logging it there is no way to connect a
    // report of "it broke" to anything.
    console.error('Page error', error.digest ?? '', error)
  }, [error])

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <h1 className="text-xl font-medium tracking-tight">Something broke on this page.</h1>
      <p className="text-ink-2 mt-3 text-[0.9375rem] leading-relaxed">
        That&rsquo;s our fault, not yours. The market data is unaffected — try loading it
        again.
      </p>
      <div className="mt-6 flex items-center gap-5">
        <button
          type="button"
          onClick={reset}
          className="border-rule hover:border-rule-strong rounded-md border px-3.5 py-2 text-[0.8125rem] transition-colors"
        >
          Try again
        </button>
        {/* A plain anchor, not next/link, on purpose: client-side navigation
            reuses the React tree that just crashed, while a hard load rebuilds
            it from scratch. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/" className="text-ink-3 hover:text-ink text-[0.8125rem] transition-colors">
          Back to your stocks
        </a>
      </div>
      {error.digest && (
        <p className="text-ink-3 mt-8 font-mono text-[0.75rem]">Reference: {error.digest}</p>
      )}
    </main>
  )
}
