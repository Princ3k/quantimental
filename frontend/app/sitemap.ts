import type { MetadataRoute } from 'next'

import { SITE_URL, getSnapshot } from '@/lib/snapshot'

/**
 * Every page worth indexing.
 *
 * The per-stock pages are the reason this file exists: 503 URLs, each leading
 * with a plain sentence about a named company, is the app's only route to
 * being found by anyone who wasn't already sent a link.
 */
export const revalidate = 86_400

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const snapshot = await getSnapshot()

  const home: MetadataRoute.Sitemap = [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1,
    },
  ]

  if (!snapshot) return home

  // The scan runs on a schedule, so every stock page changes when it does.
  const lastModified = snapshot.generated_at ? new Date(snapshot.generated_at) : new Date()

  return [
    ...home,
    ...snapshot.stocks.map((stock) => ({
      url: `${SITE_URL}/stock/${stock.t.toLowerCase()}`,
      lastModified,
      changeFrequency: 'daily' as const,
      priority: 0.7,
    })),
  ]
}
