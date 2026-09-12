import path from 'node:path'
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Type errors fail the build on purpose. The previous config set
  // `typescript.ignoreBuildErrors: true`, which meant real type errors
  // shipped to production silently. (Linting is run separately via
  // `npm run lint`; Next 16 no longer accepts an `eslint` key here.)
  typescript: { ignoreBuildErrors: false },

  // Pin the workspace root to this package. Turbopack otherwise walks up
  // looking for a lockfile and can settle on the user's home directory.
  turbopack: { root: path.join(__dirname) },

  // Note: next/image is deliberately NOT configured for remote hosts.
  // News thumbnails come from arbitrary publisher domains, and a wildcard
  // `remotePatterns` turns the Image Optimization endpoint into an open proxy
  // that anyone can point at any URL to burn CPU and disk
  // (GHSA-9g9p-9gw9-jx7f). Article images use a plain <img> so they bypass
  // the optimizer entirely.
}

export default nextConfig
