import next from 'eslint-config-next'

/**
 * ESLint flat config.
 *
 * `eslint-config-next` 16 ships a flat config directly, so the old
 * `FlatCompat` shim around "next/core-web-vitals" is gone — under ESLint 9
 * that combination threw a circular-structure error and lint never ran at all.
 */
const config = [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
  ...next,
  {
    rules: {
      // Article thumbnails come from arbitrary publisher domains and are
      // served with a plain <img> on purpose, to keep Next's image optimizer
      // from acting as an open proxy. See next.config.ts.
      '@next/next/no-img-element': 'off',
    },
  },
]

export default config
