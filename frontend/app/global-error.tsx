'use client'

/**
 * The last resort: an error in the root layout itself.
 *
 * This replaces the entire document, so it must render its own <html> and
 * <body> — and it cannot rely on the app's stylesheet, which lives in the
 * layout that just failed. Hence the inline styles, and hence the deliberately
 * plain look.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#fafaf9',
          color: '#1c1b1a',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          padding: '1.5rem',
        }}
      >
        <div style={{ maxWidth: '26rem' }}>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 500, margin: 0 }}>
            Quantimental failed to load.
          </h1>
          <p style={{ marginTop: '0.75rem', lineHeight: 1.6, color: '#57534e' }}>
            Something went wrong before the page could start. Reloading usually fixes it.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: '1.5rem',
              padding: '0.5rem 0.875rem',
              fontSize: '0.875rem',
              border: '1px solid #d6d3d1',
              borderRadius: '0.375rem',
              background: 'transparent',
              color: 'inherit',
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  )
}
